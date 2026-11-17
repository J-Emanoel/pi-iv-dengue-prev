"""Consolida as referências populacionais IBGE por município e ano de aplicação."""

import argparse
import csv
import hashlib
import html
import io
import json
import re
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path

import requests

from pipelines.arquivos import sha256_arquivo
from pipelines.etl_ibge import MANIFESTO, carregar_cadastro

ROOT = Path(__file__).resolve().parents[1]
FONTES_DIR = ROOT / "data/raw/populacao"
OUTPUT_CSV = ROOT / "data/processed/populacao_municipal.csv"
OUTPUT_JSON = ROOT / "data/processed/populacao_municipal_resumo.json"
BASE_URL = "https://ftp.ibge.gov.br/"
FONTES = {
    2020: ("Estimativas_de_Populacao/Estimativas_2020/POP2020_20220905.ods", "d42425964927f97801e658e746ff469096818826dff125fd838fc9bf3840b6cc"),
    2021: ("Estimativas_de_Populacao/Estimativas_2021/POP2021_20240624.ods", "909da50040de6054ee2bd4a555631c83c591b72ec0c4fdb20f08a4eb881b83cb"),
    2023: ("Informacoes_Gerais_e_Referencia/Relacao_da_Populacao_dos_Municipios_para_publicacao_no_DOU_em_2023/POP_TCU_2023_Municipios_POP2022_Malha2023.ods", "d36756308567aa3e7252778400d6c070087e498d24fce28217c01f748962d781"),
    2024: ("Estimativas_de_Populacao/Estimativas_2024/POP2024_20241230.ods", "a1a05b51982d8ac398f1069bf2f2756c13d7b785c92302146bd490c266e14664"),
    2025: ("Estimativas_de_Populacao/Estimativas_2025/POP2025_20260828.ods", "748303510fb724f11a6e36b3d3ba19d1655397cacabe7dad5ba82ac11d781629"),
    2026: ("Estimativas_de_Populacao/Estimativas_2026/POP2026_20261029.ods", "3ffcd867aecc8d144ef309e597976e84666d192811256f917bc8d6045f1301a7"),
}
COLUNAS = (
    "codigo_ibge", "ano", "codigo_ibge_completo", "populacao", "data_referencia",
    "tipo", "fonte_url", "fonte_sha256", "observacao",
)
T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
X = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
O = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"


def baixar_fontes(pasta=FONTES_DIR):
    """Baixa versões fixadas; reutiliza arquivos locais com o checksum correto."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    for caminho, digest in FONTES.values():
        destino = pasta / Path(caminho).name
        if destino.is_file() and sha256_arquivo(destino) == digest:
            continue
        resposta = requests.get(BASE_URL + caminho, timeout=30)
        resposta.raise_for_status()
        if hashlib.sha256(resposta.content).hexdigest() != digest:
            raise ValueError(f"Fonte oficial mudou de versão: {destino.name}. Revise antes de usar.")
        destino.write_bytes(resposta.content)


def ler_estimativa_ods(caminho):
    """Lê as cinco primeiras colunas das tabelas municipais oficiais em ODS."""
    with zipfile.ZipFile(caminho) as archive:
        root = ET.fromstring(archive.read("content.xml"))
    resultado = {}
    for table in root.iter(T + "table"):
        cabecalho = False
        for row in table.findall(T + "table-row"):
            valores = []
            for cell in list(row):
                valor = cell.get(O + "value") or " ".join(
                    "".join(p.itertext()) for p in cell.findall(X + "p")
                )
                repeticoes = min(int(cell.get(T + "number-columns-repeated", "1")), 5 - len(valores))
                valores.extend([valor.strip()] * repeticoes)
                if len(valores) == 5:
                    break
            if valores[:3] == ["UF", "COD. UF", "COD. MUNIC"]:
                if len(valores) != 5 or "POPULA" not in valores[4]:
                    raise ValueError("Cabeçalho populacional incompatível.")
                cabecalho = True
                continue
            if not cabecalho or not valores or valores[0] != "ES":
                continue
            if len(valores) != 5 or valores[1] != "32" or not valores[2].isdigit():
                raise ValueError("Linha municipal ODS incompatível.")
            codigo = valores[1] + valores[2].zfill(5)
            if not re.fullmatch(r"32\d{5}", codigo) or not valores[4].isdigit():
                raise ValueError("Código ou população inválidos na fonte ODS.")
            if codigo in resultado or int(valores[4]) <= 0:
                raise ValueError("Código repetido ou população não positiva.")
            resultado[codigo] = int(valores[4])
    return resultado


def ler_censo_zip(zip_path):
    """Lê somente a população censitária 2022 da exportação recebida."""
    manifesto = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    fonte = next(item for item in manifesto["packages"] if item["source"].startswith("IBGE"))
    with zipfile.ZipFile(zip_path) as archive:
        arquivos = [info for info in archive.infolist() if Path(info.filename).name == fonte["filename"]]
        if len(arquivos) != 1:
            raise ValueError("Esperada uma única exportação IBGE no ZIP.")
        raw = archive.read(arquivos[0])
    digest = hashlib.sha256(raw).hexdigest()
    if digest != fonte["sha256"]:
        raise ValueError("Exportação censitária diferente do inventário.")
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig")), strict=True)
    next(reader)
    header = [html.unescape(value) for value in next(reader)]
    codigo = next(i for i, value in enumerate(header) if value.startswith("Código"))
    indices = [i for i, value in enumerate(header) if "último censo" in value and "[2022]" in value]
    if len(indices) != 1:
        raise ValueError("Referência censitária 2022 não identificada.")
    resultado = {}
    for row in reader:
        if not row or not any(row):
            continue
        if row[0].startswith("<"):
            break
        if len(row) != len(header) or not row[indices[0]].isdigit() or row[codigo] in resultado:
            raise ValueError("Linha censitária inválida ou repetida.")
        resultado[row[codigo]] = int(row[indices[0]])
    return resultado, digest, fonte["filename"]


def validar_populacoes(registros, cadastro, anos=range(2020, 2027)):
    mapa = {row["codigo_municipio"]: row["codigo_ibge_completo"] for row in cadastro}
    esperadas = {(codigo, ano) for codigo in mapa for ano in anos}
    chaves = set()
    for row in registros:
        chave = row["codigo_ibge"], row["ano"]
        if chave in chaves or chave not in esperadas or mapa[chave[0]] != row["codigo_ibge_completo"]:
            raise ValueError("Chave populacional duplicada, fora do período ou sem correspondência.")
        if type(row["populacao"]) is not int or row["populacao"] <= 0:
            raise ValueError("População precisa ser um inteiro positivo.")
        referencia = date.fromisoformat(row["data_referencia"])
        if row["ano"] in (2022, 2023):
            tipo = "censo" if row["ano"] == 2022 else "relacao_censitaria"
            if referencia != date(2022, 8, 1) or row["tipo"] != tipo:
                raise ValueError("Referência censitária incompatível.")
        elif referencia != date(row["ano"], 7, 1) or row["tipo"] != "estimativa":
            raise ValueError("Referência da estimativa incompatível com o ano.")
        if not row["fonte_url"] or not re.fullmatch(r"[a-f0-9]{64}", row["fonte_sha256"]):
            raise ValueError("Fonte ou checksum populacional inválidos.")
        chaves.add(chave)
    if chaves != esperadas:
        raise ValueError("Série populacional incompleta para os municípios e anos esperados.")


def processar_populacao(zip_path=ROOT / "arquivos-proj-int-iv.zip", pasta=FONTES_DIR,
                       output_csv=OUTPUT_CSV, output_json=OUTPUT_JSON):
    cadastro = carregar_cadastro()
    codigos = {row["codigo_ibge_completo"] for row in cadastro}
    registros = []
    censo, censo_hash, censo_nome = ler_censo_zip(zip_path)
    for ano in range(2020, 2027):
        if ano == 2022:
            valores, digest = censo, censo_hash
            url = f"zip://arquivos-proj-int-iv.zip/{censo_nome}"
            referencia, tipo = "2022-08-01", "censo"
            nota = "Censo 2022 da exportação IBGE recebida; não é estimativa anual."
        else:
            caminho, digest = FONTES[ano]
            local = Path(pasta) / Path(caminho).name
            if not local.is_file() or sha256_arquivo(local) != digest:
                raise ValueError(f"Fonte {ano} ausente ou diferente da versão fixada; execute com --baixar.")
            valores, url = ler_estimativa_ods(local), BASE_URL + caminho
            referencia, tipo, nota = f"{ano}-07-01", "estimativa", "Estimativa oficial na versão indicada pela fonte."
            if ano == 2023:
                referencia, tipo = "2022-08-01", "relacao_censitaria"
                nota = "Publicação TCU 2023 baseada no Censo 2022 e malha 2023; não é estimativa independente de 2023."
        if set(valores) != codigos:
            raise ValueError(f"Fonte {ano} não cobre exatamente os 78 códigos do cadastro.")
        for codigo in sorted(codigos):
            registros.append(dict(
                codigo_ibge=codigo[:6], ano=ano, codigo_ibge_completo=codigo,
                populacao=valores[codigo], data_referencia=referencia, tipo=tipo,
                fonte_url=url, fonte_sha256=digest, observacao=nota,
            ))
    validar_populacoes(registros, cadastro)
    output_csv, output_json = Path(output_csv), Path(output_json)
    if len({output_csv.resolve(), output_json.resolve(), Path(zip_path).resolve()}) != 3:
        raise ValueError("Caminhos de entrada e saída devem ser distintos.")
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=output_csv.parent, delete=False) as stream:
            temporario = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=COLUNAS)
            writer.writeheader()
            writer.writerows(registros)
        resumo = dict(
            schema_version=1, tipo="populacao_anual", fonte="IBGE", anos=list(range(2020, 2027)),
            gerado_em_utc=datetime.now(timezone.utc).isoformat(), linhas_saida=len(registros),
            csv_sha256=sha256_arquivo(temporario),
            totais_por_ano={ano: sum(row["populacao"] for row in registros if row["ano"] == ano) for ano in range(2020, 2027)},
            observacoes=["Série com referências distintas: censo, relação censitária e estimativas.", "2023 aplica a relação oficial de população 2022 com malha territorial 2023."],
        )
        temporario.replace(output_csv)
        output_json.write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        if temporario is not None:
            temporario.unlink(missing_ok=True)
    return resumo


def carregar_populacao(caminho_csv=OUTPUT_CSV, caminho_resumo=OUTPUT_JSON):
    resumo = json.loads(Path(caminho_resumo).read_text(encoding="utf-8"))
    if not isinstance(resumo, dict) or resumo.get("tipo") != "populacao_anual" or resumo.get("schema_version") != 1 or resumo.get("csv_sha256") != sha256_arquivo(caminho_csv):
        raise ValueError("População e resumo incompatíveis; gere novamente o ETL.")
    with Path(caminho_csv).open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or []) != COLUNAS:
            raise ValueError("Colunas populacionais incompatíveis.")
        registros = list(reader)
    for row in registros:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("Quantidade inesperada de campos populacionais.")
        row["ano"], row["populacao"] = int(row["ano"]), int(row["populacao"])
    validar_populacoes(registros, carregar_cadastro())
    if resumo.get("linhas_saida") != len(registros):
        raise ValueError("Quantidade populacional diverge do resumo.")
    totais = {str(ano): sum(row["populacao"] for row in registros if row["ano"] == ano) for ano in range(2020, 2027)}
    if resumo.get("totais_por_ano") != totais:
        raise ValueError("Totais populacionais divergem do resumo.")
    return registros


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baixar", action="store_true", help="Obtém as versões oficiais fixadas e reutiliza cópias já válidas.")
    args = parser.parse_args()
    try:
        if args.baixar:
            baixar_fontes()
        resumo = processar_populacao()
        print(json.dumps(resumo, ensure_ascii=True, indent=2))
        return 0
    except (OSError, ValueError, KeyError, csv.Error, zipfile.BadZipFile, ET.ParseError, requests.RequestException) as exc:
        print(f"Erro no ETL populacional: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
