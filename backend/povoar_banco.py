"""Confere e sincroniza os agregados, corrigindo duplicações sem somá-las."""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import bindparam, delete, func, insert, inspect, select, text, update
from sqlalchemy.exc import SQLAlchemyError

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.database import Base, DatabaseConfigurationError, get_engine, transacao
from backend.analitica import ANOS_SESA, gerar_calendario, preparar_base_analitica
from backend.models import (
    CasoDengue, ClimaSemanal, EstacaoMeteorologica, Municipio, NotificacaoEstadual,
    PopulacaoMunicipal, VinculoMunicipioEstacao,
)
from pipelines.arquivos import sha256_arquivo
from pipelines.calendario import semanas_no_ano
from pipelines.etl_ibge import (
    OUTPUT_CSV as DEFAULT_CADASTRO_CSV,
    OUTPUT_JSON as DEFAULT_CADASTRO_SUMMARY,
    carregar_cadastro,
    validar_cadastro,
)
from pipelines.etl_populacao import (
    OUTPUT_CSV as DEFAULT_POP_CSV,
    OUTPUT_JSON as DEFAULT_POP_SUMMARY,
    COLUNAS as COLUNAS_POPULACAO,
    carregar_populacao,
    validar_populacoes,
)
from pipelines.etl_inmet import (
    CLIMA_CSV, ESTACOES_CSV, RESUMO_JSON as CLIMA_RESUMO,
    COLUNAS_CLIMA, COLUNAS_ESTACOES, carregar_clima, validar_clima,
)
from pipelines.vincular_estacoes import (
    COLUNAS as COLUNAS_VINCULOS, OUTPUT_CSV as VINCULOS_CSV, OUTPUT_JSON as VINCULOS_RESUMO,
    carregar_vinculos, validar_vinculos,
)
from pipelines.avaliar_fontes import (
    CANDIDATA_CSV, RESUMO_AVALIACAO, COLUNAS_BANCO_SESA, carregar_serie_sesa, validar_serie_sesa,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data/processed/dengue_semanal.csv"
DEFAULT_SUMMARY = ROOT / "data/processed/dengue_semanal_resumo.json"
DEFAULT_BACKUP = ROOT / "data/interim/backups"
ATUALIZACAO_CSV = ROOT / "data/processed/atualizacao_2026/dengue_semanal.csv"
ATUALIZACAO_RESUMO = ROOT / "data/processed/atualizacao_2026/dengue_semanal_resumo.json"


@dataclass
class FonteCarga:
    """Agregados validados e anos que a sincronização pode modificar."""

    registros: list[dict]
    anos: list[int]


@dataclass(frozen=True)
class CargaPreparada:
    """Fonte já validada, operação correspondente e resumo para conferência."""

    fonte: object
    sincronizar: Callable
    resumo: str


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


def salvar_backup(rows, pasta, *, tabela="casos"):
    """Guarda os agregados existentes antes de qualquer correção ou exclusão."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = pasta / f"{tabela}_antes_sincronizacao_{stamp}.csv"
    campos = {
        "casos": ["id", "codigo_ibge", "ano", "semana_epidemiologica", "quantidade_casos"],
        "municipios": ["codigo_ibge", "nome", "populacao"],
        "populacao": list(COLUNAS_POPULACAO),
        "estacoes": list(COLUNAS_ESTACOES),
        "clima": list(COLUNAS_CLIMA),
        "vinculos": list(COLUNAS_VINCULOS),
        "sesa": list(COLUNAS_BANCO_SESA),
    }
    # O backup é somente de registros agregados, não de pessoas.
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=campos[tabela])
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
    with transacao(engine) as connection:
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


def sincronizar_municipios(engine, registros, *, backup_dir=DEFAULT_BACKUP):
    """Atualiza o cadastro nominal sem alterar população, códigos ou casos."""
    validar_cadastro(registros, quantidade_esperada=None)
    esperados = {row["codigo_municipio"]: row["nome"] for row in registros}
    tabela = Municipio.__table__
    resultado = dict(inseridos=0, atualizados=0, mantidos=0, backup=None)
    with engine.begin() as connection:
        Base.metadata.create_all(bind=connection)
        if connection.dialect.name == "postgresql":
            connection.execute(text("LOCK TABLE municipios IN SHARE ROW EXCLUSIVE MODE"))
        atuais = list(connection.execute(select(tabela).order_by(tabela.c.codigo_ibge)).mappings())
        por_codigo = {row["codigo_ibge"]: row for row in atuais}
        codigos_casos = set(connection.execute(select(CasoDengue.codigo_ibge).distinct()).scalars())
        if (set(por_codigo) | codigos_casos) - set(esperados):
            raise ValueError("O banco contém códigos sem correspondência no cadastro IBGE.")
        alteracoes = [
            {"codigo_alvo": codigo, "novo_nome": nome}
            for codigo, nome in esperados.items()
            if codigo in por_codigo and por_codigo[codigo]["nome"] != nome
        ]
        novos = [
            dict(codigo_ibge=codigo, nome=nome)
            for codigo, nome in esperados.items() if codigo not in por_codigo
        ]
        if alteracoes:
            resultado["backup"] = salvar_backup(atuais, backup_dir, tabela="municipios")
        for lote in blocos(alteracoes):
            connection.execute(
                update(tabela).where(tabela.c.codigo_ibge == bindparam("codigo_alvo"))
                .values(nome=bindparam("novo_nome")), lote,
            )
        for lote in blocos(novos):
            connection.execute(insert(tabela), lote)
        resultado["atualizados"] = len(alteracoes)
        resultado["inseridos"] = len(novos)
        resultado["mantidos"] = len(esperados) - len(alteracoes) - len(novos)
    return resultado


def sincronizar_populacoes(engine, registros, *, backup_dir=DEFAULT_BACKUP):
    """Sincroniza somente a população anual; casos e cadastro ficam intactos."""
    if not registros:
        raise ValueError("Fonte populacional vazia.")
    cadastro = list({row["codigo_ibge"]: dict(
        codigo_municipio=row["codigo_ibge"], codigo_ibge_completo=row["codigo_ibge_completo"],
    ) for row in registros}.values())
    anos = sorted({row["ano"] for row in registros})
    validar_populacoes(registros, cadastro, anos)
    preparados = [{**row, "data_referencia": date.fromisoformat(row["data_referencia"])} for row in registros]
    tabela = PopulacaoMunicipal.__table__
    campos = [column.name for column in tabela.columns if not column.primary_key]
    resultado = dict(inseridos=0, atualizados=0, mantidos=0, backup=None)
    with engine.begin() as connection:
        if not inspect(connection).has_table("municipios"):
            raise ValueError("Carregue primeiro o cadastro municipal.")
        existentes = set(connection.execute(select(Municipio.codigo_ibge)).scalars())
        if {row["codigo_ibge"] for row in preparados} - existentes:
            raise ValueError("População com municípios ainda não cadastrados no banco.")
        tabela.create(bind=connection, checkfirst=True)
        if connection.dialect.name == "postgresql":
            connection.execute(text("LOCK TABLE populacoes_municipais IN SHARE ROW EXCLUSIVE MODE"))
        atuais = list(connection.execute(select(tabela).where(tabela.c.ano.in_(anos))).mappings())
        por_chave = {(row["codigo_ibge"], row["ano"]): row for row in atuais}
        novas_chaves = {(row["codigo_ibge"], row["ano"]) for row in preparados}
        if set(por_chave) - novas_chaves:
            raise ValueError("População existente fora da fonte nos anos cobertos; revise o cadastro.")
        insercoes, alteracoes = [], []
        for row in preparados:
            anterior = por_chave.get((row["codigo_ibge"], row["ano"]))
            if anterior is None:
                insercoes.append(row)
            elif any(anterior[campo] != row[campo] for campo in campos):
                alteracoes.append({"codigo_alvo": row["codigo_ibge"], "ano_alvo": row["ano"],
                                   **{"novo_" + campo: row[campo] for campo in campos}})
        if alteracoes:
            resultado["backup"] = salvar_backup(atuais, backup_dir, tabela="populacao")
        for lote in blocos(insercoes):
            connection.execute(insert(tabela), lote)
        for lote in blocos(alteracoes):
            connection.execute(update(tabela).where(
                tabela.c.codigo_ibge == bindparam("codigo_alvo"), tabela.c.ano == bindparam("ano_alvo"),
            ).values({campo: bindparam("novo_" + campo) for campo in campos}), lote)
        resultado.update(inseridos=len(insercoes), atualizados=len(alteracoes),
                         mantidos=len(preparados) - len(insercoes) - len(alteracoes),
                         linhas_no_periodo=connection.scalar(select(func.count()).select_from(tabela).where(tabela.c.ano.in_(anos))))
    return resultado


def sincronizar_clima(engine, fonte, *, backup_dir=DEFAULT_BACKUP):
    """Sincroniza estações e semanas em uma transação, sem alterar as outras bases."""
    estacoes, semanas = fonte
    validar_clima(estacoes, semanas)
    preparados = [{**row, "data_inicio": date.fromisoformat(row["data_inicio"]),
                   "inicio_utc": datetime.fromisoformat(row["inicio_utc"]),
                   "fim_utc": datetime.fromisoformat(row["fim_utc"])} for row in semanas]
    anos = sorted({row["ano"] for row in semanas})

    def normalizar(row):
        resultado = dict(row)
        for campo in ("inicio_utc", "fim_utc"):
            if campo in resultado:
                valor = resultado[campo]
                resultado[campo] = valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor.astimezone(timezone.utc)
        return resultado

    with transacao(engine) as connection:
        EstacaoMeteorologica.__table__.create(bind=connection, checkfirst=True)
        ClimaSemanal.__table__.create(bind=connection, checkfirst=True)
        if connection.dialect.name == "postgresql":
            connection.execute(text("LOCK TABLE estacoes_inmet, clima_semanal IN SHARE ROW EXCLUSIVE MODE"))

        def sincronizar_tabela(tabela, registros, tipo, condicao=None):
            chaves = [column.name for column in tabela.primary_key.columns]
            campos = [column.name for column in tabela.columns if not column.primary_key]
            consulta = select(tabela)
            if condicao is not None:
                consulta = consulta.where(condicao)
            atuais = [normalizar(row) for row in connection.execute(consulta).mappings()]
            por_chave = {tuple(row[campo] for campo in chaves): row for row in atuais}
            esperadas = {tuple(row[campo] for campo in chaves) for row in registros}
            if tipo == "clima" and set(por_chave) - esperadas:
                raise ValueError("O banco contém semanas fora da fonte nos anos cobertos; revise antes da carga.")
            insercoes, alteracoes = [], []
            for row in registros:
                anterior = por_chave.get(tuple(row[campo] for campo in chaves))
                if anterior is None:
                    insercoes.append(row)
                elif any(anterior[campo] != row[campo] for campo in campos):
                    alteracoes.append({**{"alvo_" + campo: row[campo] for campo in chaves},
                                       **{"novo_" + campo: row[campo] for campo in campos}})
            backup = salvar_backup(atuais, backup_dir, tabela=tipo) if alteracoes else None
            for lote in blocos(insercoes):
                connection.execute(insert(tabela), lote)
            for lote in blocos(alteracoes):
                connection.execute(update(tabela).where(*[
                    tabela.c[campo] == bindparam("alvo_" + campo) for campo in chaves
                ]).values({campo: bindparam("novo_" + campo) for campo in campos}), lote)
            return dict(inseridos=len(insercoes), atualizados=len(alteracoes),
                        mantidos=len(registros) - len(insercoes) - len(alteracoes), backup=backup)

        resultado = {
            "estacoes": sincronizar_tabela(EstacaoMeteorologica.__table__, estacoes, "estacoes"),
            "semanas": sincronizar_tabela(ClimaSemanal.__table__, preparados, "clima", ClimaSemanal.ano.in_(anos)),
        }
    return resultado


def sincronizar_vinculos(engine, registros, *, backup_dir=DEFAULT_BACKUP):
    """Sincroniza somente os vínculos; exige municípios e estações já cadastrados."""
    validar_vinculos(registros)
    tabela = VinculoMunicipioEstacao.__table__
    anos = sorted({row["ano"] for row in registros})
    campos = [column.name for column in tabela.columns if not column.primary_key]
    with transacao(engine) as connection:
        if any(not inspect(connection).has_table(nome) for nome in ("municipios", "estacoes_inmet")):
            raise ValueError("Carregue primeiro os municípios e as estações INMET.")
        municipios = set(connection.execute(select(Municipio.codigo_ibge)).scalars())
        estacoes = set(connection.execute(select(EstacaoMeteorologica.codigo)).scalars())
        if {row["codigo_ibge"] for row in registros} - municipios or {row["codigo_estacao"] for row in registros} - estacoes:
            raise ValueError("Vínculos com município ou estação ainda não cadastrados.")
        tabela.create(bind=connection, checkfirst=True)
        if connection.dialect.name == "postgresql":
            connection.execute(text("LOCK TABLE municipios_estacoes IN SHARE ROW EXCLUSIVE MODE"))
        atuais = list(connection.execute(select(tabela).where(tabela.c.ano.in_(anos))).mappings())
        por_chave = {(row["codigo_ibge"], row["ano"]): row for row in atuais}
        esperadas = {(row["codigo_ibge"], row["ano"]) for row in registros}
        if set(por_chave) - esperadas:
            raise ValueError("Vínculos existentes fora da fonte nos anos cobertos; revise antes da carga.")
        insercoes, alteracoes = [], []
        for row in registros:
            anterior = por_chave.get((row["codigo_ibge"], row["ano"]))
            if anterior is None:
                insercoes.append(row)
            elif any(anterior[campo] != row[campo] for campo in campos):
                alteracoes.append({"codigo_alvo": row["codigo_ibge"], "ano_alvo": row["ano"],
                                   **{"novo_" + campo: row[campo] for campo in campos}})
        backup = salvar_backup(atuais, backup_dir, tabela="vinculos") if alteracoes else None
        for lote in blocos(insercoes):
            connection.execute(insert(tabela), lote)
        for lote in blocos(alteracoes):
            connection.execute(update(tabela).where(
                tabela.c.codigo_ibge == bindparam("codigo_alvo"), tabela.c.ano == bindparam("ano_alvo"),
            ).values({campo: bindparam("novo_" + campo) for campo in campos}), lote)
    return dict(inseridos=len(insercoes), atualizados=len(alteracoes),
                mantidos=len(registros) - len(insercoes) - len(alteracoes), backup=backup)


def sincronizar_sesa(engine, registros, *, backup_dir=DEFAULT_BACKUP):
    """Carga estadual em tabela própria; nunca modifica registros SINAN."""
    validar_serie_sesa(registros)
    tabela = NotificacaoEstadual.__table__
    anos = sorted({row["ano"] for row in registros})
    chaves = ("codigo_ibge", "ano", "semana_epidemiologica")
    campos = [column.name for column in tabela.columns if not column.primary_key]
    def chave_sesa(row):
        return tuple(row[campo] for campo in chaves)
    with engine.begin() as connection:
        if not inspect(connection).has_table("municipios"):
            raise ValueError("Carregue primeiro o cadastro municipal.")
        municipios = set(connection.execute(select(Municipio.codigo_ibge)).scalars())
        if {row["codigo_ibge"] for row in registros} - municipios:
            raise ValueError("SESA com município ainda não cadastrado.")
        tabela.create(bind=connection, checkfirst=True)
        if connection.dialect.name == "postgresql":
            connection.execute(text("LOCK TABLE notificacoes_sesa IN SHARE ROW EXCLUSIVE MODE"))
        atuais = list(connection.execute(select(tabela).where(tabela.c.ano.in_(anos))).mappings())
        por_chave = {chave_sesa(row): row for row in atuais}
        if set(por_chave) - {chave_sesa(row) for row in registros}:
            raise ValueError("SESA existente fora da fonte no período; revise antes de substituir dados.")
        insercoes, alteracoes = [], []
        for row in registros:
            anterior = por_chave.get(chave_sesa(row))
            if anterior is None:
                insercoes.append(row)
            elif any(anterior[campo] != row[campo] for campo in campos):
                alteracoes.append({**{"alvo_" + campo: row[campo] for campo in chaves},
                                   **{"novo_" + campo: row[campo] for campo in campos}})
        backup = salvar_backup(atuais, backup_dir, tabela="sesa") if alteracoes else None
        for lote in blocos(insercoes):
            connection.execute(insert(tabela), lote)
        for lote in blocos(alteracoes):
            connection.execute(update(tabela).where(*[
                tabela.c[campo] == bindparam("alvo_" + campo) for campo in chaves
            ]).values({campo: bindparam("novo_" + campo) for campo in campos}), lote)
    return dict(inseridos=len(insercoes), atualizados=len(alteracoes),
                mantidos=len(registros) - len(insercoes) - len(alteracoes), backup=backup)


def sincronizar_atualizacao_2026(engine, fonte, clima, vinculos, *, backup_dir=DEFAULT_BACKUP):
    """Atualiza somente o SINAN 2026 e integra INMET/vínculos numa transação única."""
    if fonte.anos != [2026] or {r["ano"] for r in fonte.registros} != {2026}:
        raise ValueError("A carga conjunta exige uma fonte SINAN exclusiva de 2026.")
    validar_clima(*clima)
    validar_vinculos(vinculos)
    if 2026 not in {r["ano"] for r in clima[1]} or 2026 not in {r["ano"] for r in vinculos}:
        raise ValueError("A carga conjunta exige clima e vínculos de 2026.")
    with transacao(engine) as connection:
        def snapshot(modelo, condicao=None):
            tabela = modelo.__table__
            if not inspect(connection).has_table(tabela.name):
                return []
            query = select(tabela).order_by(*tabela.primary_key.columns)
            if condicao is not None:
                query = query.where(condicao)
            return [dict(row) for row in connection.execute(query).mappings()]

        protegidas = (Municipio, PopulacaoMunicipal, NotificacaoEstadual)
        antes = {modelo: snapshot(modelo) for modelo in protegidas}
        casos_anteriores = snapshot(CasoDengue, CasoDengue.ano != 2026)
        codigos = {r["codigo_ibge"] for r in antes[Municipio]}
        if not codigos or {r["codigo_ibge"] for r in fonte.registros} - codigos:
            raise ValueError("Prepare o cadastro municipal antes da atualização de 2026.")
        if {r["codigo_ibge"] for r in vinculos if r["ano"] == 2026} != codigos:
            raise ValueError("Os vínculos de 2026 devem cobrir todos os municípios cadastrados.")
        resultado = dict(
            sinan=sincronizar_casos(connection, fonte, backup_dir=backup_dir),
            clima=sincronizar_clima(connection, clima, backup_dir=backup_dir),
            vinculos=sincronizar_vinculos(connection, vinculos, backup_dir=backup_dir),
        )
        if any(snapshot(modelo) != antes[modelo] for modelo in protegidas):
            raise ValueError("Cadastro, população ou notificações SESA foram alterados; atualização revertida.")
        if snapshot(CasoDengue, CasoDengue.ano != 2026) != casos_anteriores:
            raise ValueError("SINAN de outros anos foi alterado; atualização revertida.")
    return resultado


def criar_parser():
    """Declara os modos de carga; nenhum deles aplica alterações por padrão."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--resumo", type=Path)
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--municipios", action="store_true", help="Confere ou atualiza somente o cadastro nominal IBGE.")
    modo.add_argument("--populacao", action="store_true", help="Confere ou sincroniza somente a população por município/ano.")
    modo.add_argument("--clima", action="store_true", help="Confere ou sincroniza estações e clima semanal INMET.")
    modo.add_argument("--vinculos", action="store_true", help="Confere ou sincroniza vínculos geográficos por município/ano.")
    modo.add_argument("--analitica", action="store_true", help="Prepara o calendário e a visão integrada, preservando as fontes.")
    modo.add_argument("--sesa", action="store_true", help="Confere ou carrega somente a série estadual por notificação.")
    modo.add_argument("--analitica-sesa", action="store_true", help="Prepara a visão estadual integrada de 2020–2024.")
    modo.add_argument("--atualizacao-2026", action="store_true", help="Sincroniza SINAN 2026, clima e vínculos em transação única.")
    parser.add_argument("--estacoes", type=Path, default=ESTACOES_CSV, help="CSV de estações, utilizado no modo --clima.")
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP)
    parser.add_argument("--aplicar", action="store_true", help="Sincroniza o banco configurado em DATABASE_URL.")
    return parser


def _preparar_carga(args) -> CargaPreparada:
    """Associa cada fonte ao seu sincronizador no mesmo ponto do código."""
    if args.sesa:
        fonte = carregar_serie_sesa(args.input or CANDIDATA_CSV, args.resumo or RESUMO_AVALIACAO)
        resumo = f"Série estadual validada: {len(fonte)} agregados; {sum(row['registros_notificados'] for row in fonte)} registros por notificação."
        return CargaPreparada(fonte, sincronizar_sesa, resumo)
    if args.vinculos:
        fonte = carregar_vinculos(args.input or VINCULOS_CSV, args.resumo or VINCULOS_RESUMO)
        resumo = f"Vínculos validados: {len(fonte)} associações anuais por proximidade geográfica."
        return CargaPreparada(fonte, sincronizar_vinculos, resumo)
    if args.clima:
        fonte = carregar_clima(args.input or CLIMA_CSV, args.resumo or CLIMA_RESUMO, args.estacoes)
        resumo = f"Clima validado: {len(fonte[0])} estações; {len(fonte[1])} semanas. Vínculos municipais são carregados com --vinculos."
        return CargaPreparada(fonte, sincronizar_clima, resumo)
    if args.populacao:
        fonte = carregar_populacao(args.input or DEFAULT_POP_CSV, args.resumo or DEFAULT_POP_SUMMARY)
        resumo = f"População validada: {len(fonte)} registros por município/ano, com referências documentadas."
        return CargaPreparada(fonte, sincronizar_populacoes, resumo)
    if args.municipios:
        fonte = carregar_cadastro(args.input or DEFAULT_CADASTRO_CSV, args.resumo or DEFAULT_CADASTRO_SUMMARY)
        resumo = f"Cadastro nominal validado: {len(fonte)} municípios; população preservada."
        return CargaPreparada(fonte, sincronizar_municipios, resumo)
    fonte = carregar_fonte(args.input or DEFAULT_CSV, args.resumo or DEFAULT_SUMMARY)
    if args.input is None and 2026 in fonte.anos:
        raise ValueError("Regere o histórico com pipelines.etl_sinan (2020–2025). Atualize 2026 pelo modo --atualizacao-2026 para não restaurar a extração antiga.")
    resumo = (f"Fonte validada: {len(fonte.registros)} linhas; "
              f"{sum(r['quantidade_casos'] for r in fonte.registros)} registros; anos {fonte.anos}.")
    return CargaPreparada(fonte, sincronizar_casos, resumo)


def _executar_carga(args):
    carga = _preparar_carga(args)
    print(carga.resumo)
    if not args.aplicar:
        print("Conferência concluída. Para sincronizar o banco, execute com --aplicar.")
        return
    resultado = carga.sincronizar(get_engine(), carga.fonte, backup_dir=args.backup_dir)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


def _executar_atualizacao_2026(args):
    """Mantém a atualização anual na operação conjunta com transação única."""
    fonte = carregar_fonte(args.input or ATUALIZACAO_CSV, args.resumo or ATUALIZACAO_RESUMO)
    clima = carregar_clima(caminho_estacoes=args.estacoes)
    vinculos = carregar_vinculos()
    if fonte.anos != [2026]:
        raise ValueError("Informe o CSV anual de 2026, separado do histórico original.")
    print(f"Atualização validada: {len(fonte.registros)} agregados SINAN; {len(clima[1])} semanas de estação; {len(vinculos)} vínculos.")
    if not args.aplicar:
        print("Conferência concluída sem conexão. Use --aplicar para a carga conjunta com backup e transação.")
        return
    resultado = sincronizar_atualizacao_2026(get_engine(), fonte, clima, vinculos, backup_dir=args.backup_dir)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


def _executar_analitica(args):
    if args.input or args.resumo:
        raise ValueError("O modo --analitica consulta as tabelas; não recebe CSV ou resumo.")
    fonte = "sesa" if args.analitica_sesa else "sinan"
    semanas = [row for row in gerar_calendario() if not args.analitica_sesa or row["ano"] in ANOS_SESA]
    print(f"Calendário validado: {len(semanas)} semanas; fonte {fonte}; visão com lacunas preservadas.")
    if not args.aplicar:
        print("Conferência concluída sem conexão. Para preparar a visão no banco, use --aplicar.")
        return
    resultado = preparar_base_analitica(get_engine(), fonte=fonte)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


def main(argv=None):
    """Escolhe o fluxo solicitado e apresenta erros sem detalhes da conexão."""
    args = criar_parser().parse_args(argv)
    try:
        if args.atualizacao_2026:
            _executar_atualizacao_2026(args)
        elif args.analitica or args.analitica_sesa:
            _executar_analitica(args)
        else:
            _executar_carga(args)
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
