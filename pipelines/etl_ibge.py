"""Extrai o cadastro municipal IBGE do ZIP e valida a correspondência com o SINAN."""

import argparse
import csv
import hashlib
import html
import io
import json
import re
import sys
import tempfile
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipelines.arquivos import sha256_arquivo

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_CSV = ROOT / "data/processed/municipios_ibge.csv"
OUTPUT_JSON = ROOT / "data/processed/municipios_ibge_resumo.json"
MANIFESTO = ROOT / "docs/inventario-bases.json"
COLUNAS = ("codigo_municipio", "codigo_ibge_completo", "nome")


def validar_cadastro(registros, quantidade_esperada=78):
    """Exige chaves únicas, códigos compatíveis e nomes preenchidos."""
    if not registros or (quantidade_esperada is not None and len(registros) != quantidade_esperada):
        raise ValueError(f"Quantidade inesperada de municípios: {len(registros)}.")
    codigos, completos = set(), set()
    for row in registros:
        codigo, completo, nome = (row.get(coluna, "") for coluna in COLUNAS)
        if not all(isinstance(value, str) for value in (codigo, completo, nome)):
            raise ValueError("Cadastro municipal com valores inválidos.")
        if (
            not re.fullmatch(r"32\d{4}", codigo)
            or not re.fullmatch(r"32\d{5}", completo)
            or completo[:6] != codigo
        ):
            raise ValueError("Código municipal inválido ou correspondência incompatível.")
        if not nome or nome != nome.strip() or "<" in nome or re.search(r"&[\w#]+;", nome):
            raise ValueError("Nome municipal ausente ou não normalizado.")
        if codigo in codigos or completo in completos:
            raise ValueError("Código municipal duplicado ou correspondência ambígua.")
        codigos.add(codigo)
        completos.add(completo)


def ler_cadastro(stream, quantidade_esperada=78):
    """Isola as linhas municipais do CSV com título, entidades HTML e notas."""
    reader = csv.reader(stream, strict=True)
    next(reader, None)  # Título da exportação do IBGE.
    header = [html.unescape(cell).strip() for cell in next(reader, [])]
    indices_nome = [i for i, cell in enumerate(header) if cell.startswith("Município")]
    indices_codigo = [i for i, cell in enumerate(header) if cell.startswith("Código")]
    if len(indices_nome) != 1 or len(indices_codigo) != 1:
        raise ValueError("Cabeçalho IBGE sem as colunas municipais esperadas.")
    registros = []
    for row in reader:
        if not row or not any(cell.strip() for cell in row):
            continue
        if row[0].lstrip().startswith("<"):
            break
        if len(row) != len(header):
            raise ValueError(f"Linha {reader.line_num}: quantidade inesperada de campos.")
        completo = row[indices_codigo[0]].strip()
        nome = unicodedata.normalize("NFC", html.unescape(row[indices_nome[0]]).strip())
        registros.append(dict(codigo_municipio=completo[:6], codigo_ibge_completo=completo, nome=nome))
    validar_cadastro(registros, quantidade_esperada)
    return sorted(registros, key=lambda row: row["codigo_municipio"])


def carregar_cadastro(caminho_csv=OUTPUT_CSV, caminho_resumo=OUTPUT_JSON):
    """Confere o par gerado pelo ETL antes de qualquer conexão ao banco."""
    caminho_csv, caminho_resumo = Path(caminho_csv), Path(caminho_resumo)
    if not caminho_csv.is_file() or not caminho_resumo.is_file():
        raise ValueError("Gere o cadastro primeiro: python -m pipelines.etl_ibge")
    resumo = json.loads(caminho_resumo.read_text(encoding="utf-8"))
    if (
        not isinstance(resumo, dict) or resumo.get("schema_version") != 1
        or resumo.get("tipo") != "cadastro_municipal" or resumo.get("fonte") != "IBGE"
        or resumo.get("csv_sha256") != sha256_arquivo(caminho_csv)
    ):
        raise ValueError("Cadastro e resumo incompatíveis. Gere novamente o ETL IBGE.")
    with caminho_csv.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or []) != COLUNAS:
            raise ValueError("Cadastro sem as colunas esperadas.")
        registros = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in registros):
        raise ValueError("Cadastro com quantidade inesperada de campos.")
    validar_cadastro(registros)
    if resumo.get("linhas_saida") != len(registros):
        raise ValueError("Quantidade de municípios diverge do resumo.")
    return registros


def processar_pacote(zip_path, output_csv=OUTPUT_CSV, output_json=OUTPUT_JSON, manifesto=MANIFESTO):
    zip_path, output_csv, output_json, manifesto = map(Path, (zip_path, output_csv, output_json, manifesto))
    if len({path.resolve() for path in (zip_path, output_csv, output_json, manifesto)}) != 4:
        raise ValueError("Originais, manifesto e saídas precisam ter caminhos distintos.")
    inventario = json.loads(manifesto.read_text(encoding="utf-8"))
    entrada_hash = sha256_arquivo(zip_path)
    if entrada_hash != inventario["input"]["sha256"]:
        raise ValueError("ZIP diferente do inventário de arquivos originais.")
    fontes = [item for item in inventario["packages"] if item["source"].startswith("IBGE")]
    if len(fontes) != 1:
        raise ValueError("Esperada uma única fonte IBGE no inventário.")
    fonte = fontes[0]
    with zipfile.ZipFile(zip_path) as archive:
        candidatos = [item for item in archive.infolist() if Path(item.filename).name == fonte["filename"]]
        if len(candidatos) != 1 or candidatos[0].file_size != fonte["bytes"]:
            raise ValueError("Arquivo IBGE ausente, ambíguo ou diferente do inventário.")
        raw = archive.read(candidatos[0])
    ibge_hash = hashlib.sha256(raw).hexdigest()
    if ibge_hash != fonte["sha256"]:
        raise ValueError("Checksum do CSV IBGE diverge do inventário.")
    registros = ler_cadastro(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=output_csv.parent, delete=False,
        ) as stream:
            temporario = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=COLUNAS)
            writer.writeheader()
            writer.writerows(registros)
        resumo = dict(
            schema_version=1, tipo="cadastro_municipal", fonte="IBGE",
            gerado_em_utc=datetime.now(timezone.utc).isoformat(),
            arquivo_entrada=zip_path.name, entrada_sha256=entrada_hash,
            arquivo_ibge=fonte["filename"], ibge_sha256=ibge_hash,
            csv_sha256=sha256_arquivo(temporario), linhas_saida=len(registros),
            observacoes=["Cadastro nominal; população será integrada com sua referência anual."],
        )
        temporario.replace(output_csv)
        output_json.write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        if temporario is not None:
            temporario.unlink(missing_ok=True)
    return resumo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "arquivos-proj-int-iv.zip")
    parser.add_argument("--output-csv", type=Path, default=OUTPUT_CSV)
    parser.add_argument("--output-json", type=Path, default=OUTPUT_JSON)
    parser.add_argument("--manifesto", type=Path, default=MANIFESTO)
    args = parser.parse_args()
    try:
        resumo = processar_pacote(args.input, args.output_csv, args.output_json, args.manifesto)
        print(f"Cadastro IBGE validado: {resumo['linhas_saida']} municípios.")
        return 0
    except (OSError, ValueError, KeyError, csv.Error, zipfile.BadZipFile) as exc:
        print(f"Erro no ETL IBGE: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
