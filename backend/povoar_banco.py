"""Confere e sincroniza os agregados, corrigindo duplicações sem somá-las."""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import bindparam, delete, func, insert, select, text, update
from sqlalchemy.exc import SQLAlchemyError

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.database import Base, DatabaseConfigurationError, get_engine
from backend.models import CasoDengue, Municipio
from pipelines.arquivos import sha256_arquivo
from pipelines.calendario import semanas_no_ano

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data/processed/dengue_semanal.csv"
DEFAULT_SUMMARY = ROOT / "data/processed/dengue_semanal_resumo.json"
DEFAULT_BACKUP = ROOT / "data/interim/backups"


@dataclass
class FonteCarga:
    """Agregados validados e anos que a sincronização pode modificar."""

    registros: list[dict]
    anos: list[int]


def carregar_fonte(caminho_csv=DEFAULT_CSV, caminho_resumo=DEFAULT_SUMMARY):
    """Valida esquema, hash, período, chaves e totais sem acessar o banco."""
    caminho_csv, caminho_resumo = Path(caminho_csv), Path(caminho_resumo)
    if not caminho_csv.is_file() or not caminho_resumo.is_file():
        raise ValueError("Gere a fonte corrigida primeiro: python -m pipelines.etl_sinan")
    summary = json.loads(caminho_resumo.read_text(encoding="utf-8"))
    if not isinstance(summary, dict):
        raise ValueError("Resumo precisa ser um objeto JSON produzido pelo ETL.")
    if (
        summary.get("schema_version") != 2
        or summary.get("localidade") != "residencia"
        or summary.get("criterio") != "registros_notificados"
    ):
        raise ValueError("Fonte antiga ou incompatível. Execute novamente pipelines.etl_sinan.")
    digest = sha256_arquivo(caminho_csv)
    if digest != summary.get("csv_sha256"):
        raise ValueError("CSV e resumo não correspondem. Execute novamente o ETL.")
    years = summary.get("anos_epidemiologicos")
    if (
        not isinstance(years, list) or not years
        or any(type(y) is not int or not 1900 <= y <= 9998 for y in years)
        or years != list(range(min(years), max(years) + 1))
    ):
        raise ValueError("Período epidemiológico inválido no resumo.")
    required = {"codigo_municipio", "ano_epidemiologico", "semana_epidemiologica", "registos"}
    records, keys = [], set()
    with caminho_csv.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("CSV sem o esquema corrigido. Gere novamente a fonte com pipelines.etl_sinan.")
        for number, row in enumerate(reader, 2):
            if None in row:
                raise ValueError(f"Linha {number}: quantidade inesperada de campos.")
            code = row["codigo_municipio"]
            values = [row[c] for c in ("ano_epidemiologico", "semana_epidemiologica", "registos")]
            if not re.fullmatch(r"32\d{4}", code or "") or not all(re.fullmatch(r"\d+", v or "") for v in values):
                raise ValueError(f"Linha {number}: código ou valores inválidos.")
            year, week, quantity = map(int, values)
            if year not in years or not 1 <= week <= semanas_no_ano(year):
                raise ValueError(f"Linha {number}: ano/semana inválidos.")
            key = code, year, week
            if key in keys:
                raise ValueError(f"Linha {number}: chave municipal/semanal duplicada no CSV.")
            keys.add(key)
            records.append(dict(
                codigo_ibge=code, ano=year,
                semana_epidemiologica=week, quantidade_casos=quantity,
            ))
    if (
        not records or len(records) != summary.get("linhas_saida")
        or sum(r["quantidade_casos"] for r in records) != summary.get("total_registos")
    ):
        raise ValueError("Totais do CSV divergem do resumo ou a fonte está vazia.")
    return FonteCarga(records, years)


def blocos(items, tamanho=500):
    """Divide operações em lotes para limitar os parâmetros enviados ao banco."""
    for start in range(0, len(items), tamanho):
        yield items[start:start + tamanho]


def chave(row):
    """Identifica um agregado: município, ano e semana epidemiológica."""
    return row["codigo_ibge"], row["ano"], row["semana_epidemiologica"]


def salvar_backup(rows, pasta):
    """Guarda os agregados existentes antes de qualquer correção ou exclusão."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = pasta / f"casos_antes_sincronizacao_{stamp}.csv"
    # O backup é somente de registros agregados, não de pessoas.
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "id", "codigo_ibge", "ano", "semana_epidemiologica", "quantidade_casos",
        ])
        writer.writeheader()
        writer.writerows(dict(row) for row in rows)
    return str(path)


def sincronizar_casos(engine, fonte, *, backup_dir=DEFAULT_BACKUP):
    """Uma transação; o CSV é a referência de quantidades para os anos cobertos.

    Mantém IDs já existentes, substitui contagens divergentes e elimina cópias.
    Não soma registros duplicados do banco. Anos fora da fonte são preservados.
    """
    cases, municipalities = CasoDengue.__table__, Municipio.__table__
    expected = {chave(r): r for r in fonte.registros}
    if not expected or len(expected) != len(fonte.registros):
        raise ValueError("Fonte vazia ou com chaves duplicadas.")
    result = dict(
        municipios_inseridos=0, inseridos=0, atualizados=0,
        duplicados_removidos=0, fora_da_fonte_removidos=0, mantidos=0, backup=None,
    )
    with engine.begin() as connection:
        Base.metadata.create_all(bind=connection)
        if connection.dialect.name == "postgresql":
            # Serializa cargas e permite que leitores mantenham seu snapshot.
            connection.execute(text("LOCK TABLE casos_dengue IN SHARE ROW EXCLUSIVE MODE"))
        outside_duplicates = connection.execute(
            select(cases.c.codigo_ibge, cases.c.ano, cases.c.semana_epidemiologica)
            .where(cases.c.ano.not_in(fonte.anos))
            .group_by(cases.c.codigo_ibge, cases.c.ano, cases.c.semana_epidemiologica)
            .having(func.count() > 1)
        ).first()
        if outside_duplicates:
            raise ValueError("Há duplicados em anos fora da fonte. Inclua esses anos na conferência antes da carga.")
        old = list(connection.execute(
            select(cases).where(cases.c.ano.in_(fonte.anos)).order_by(cases.c.id)
        ).mappings())
        grouped = defaultdict(list)
        for row in old:
            grouped[chave(row)].append(row)
        deletes, updates, inserts = [], [], []
        for key, copies in grouped.items():
            if key not in expected:
                deletes.extend(r["id"] for r in copies)
                result["fora_da_fonte_removidos"] += len(copies)
                continue
            keeper, extras = copies[0], copies[1:]
            deletes.extend(r["id"] for r in extras)
            result["duplicados_removidos"] += len(extras)
            quantity = expected[key]["quantidade_casos"]
            if keeper["quantidade_casos"] != quantity:
                updates.append((keeper["id"], quantity))
                result["atualizados"] += 1
            else:
                result["mantidos"] += 1
        inserts = [row for key, row in expected.items() if key not in grouped]
        result["inseridos"] = len(inserts)
        if deletes or updates:
            result["backup"] = salvar_backup(old, backup_dir)
        known = set(connection.execute(select(municipalities.c.codigo_ibge)).scalars())
        new_municipalities = [
            dict(codigo_ibge=code, nome=f"ES - {code}")
            for code in sorted({r["codigo_ibge"] for r in fonte.registros} - known)
        ]
        if new_municipalities:
            connection.execute(insert(municipalities), new_municipalities)
        result["municipios_inseridos"] = len(new_municipalities)
        for ids in blocos(deletes):
            connection.execute(delete(cases).where(cases.c.id.in_(ids)))
        for batch in blocos(updates):
            connection.execute(
                update(cases).where(cases.c.id == bindparam("row_id"))
                .values(quantidade_casos=bindparam("new_quantity")),
                [{"row_id": identity, "new_quantity": quantity} for identity, quantity in batch],
            )
        for batch in blocos(inserts):
            connection.execute(insert(cases), batch)
        # create_all não altera tabelas antigas: instala explicitamente o índice.
        for index in cases.indexes:
            if index.unique:
                index.create(bind=connection, checkfirst=True)
        result["linhas_no_periodo"] = connection.scalar(
            select(func.count()).select_from(cases).where(cases.c.ano.in_(fonte.anos))
        )
        result["registos_no_periodo"] = connection.scalar(
            select(func.sum(cases.c.quantidade_casos)).where(cases.c.ano.in_(fonte.anos))
        )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--resumo", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP)
    parser.add_argument("--aplicar", action="store_true", help="Sincroniza o banco configurado em DATABASE_URL.")
    args = parser.parse_args(argv)
    try:
        fonte = carregar_fonte(args.input, args.resumo)
        print(f"Fonte validada: {len(fonte.registros)} linhas; "
              f"{sum(r['quantidade_casos'] for r in fonte.registros)} registros; anos {fonte.anos}.")
        if not args.aplicar:
            print("Conferência concluída. Para sincronizar o banco, execute com --aplicar.")
            return 0
        result = sincronizar_casos(get_engine(), fonte, backup_dir=args.backup_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, DatabaseConfigurationError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
    except SQLAlchemyError:
        print("Erro na sincronização. A transação foi revertida. Confira conexão, tabelas e permissões do banco.",
              file=sys.stderr)
    return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
