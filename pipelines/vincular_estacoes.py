"""Associa municípios às estações disponíveis por ano, usando proximidade geográfica."""

import argparse
import csv
import hashlib
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests

from pipelines.arquivos import sha256_arquivo
from pipelines.etl_ibge import carregar_cadastro
from pipelines.etl_inmet import ANOS, ANOS_SUPORTADOS, RESUMO_JSON as RESUMO_CLIMA, carregar_clima, gravar_csv

ROOT = Path(__file__).resolve().parents[1]
CENTROIDES = ROOT / "data/raw/geografia/centroides_municipios_es_ibge.json"
PONTOS_SHA256 = "eb2648bf6d885ec6e8ac3a527d9da73079bfda607de7b07160a5c84dc97b4de5"
API_BASE = "https://servicodados.ibge.gov.br/api/v3/malhas/municipios"
OUTPUT_CSV = ROOT / "data/processed/vinculos_municipios_estacoes.csv"
OUTPUT_JSON = ROOT / "data/processed/vinculos_municipios_estacoes_resumo.json"
METODO = "centroide_ibge_estacao_mais_proxima_por_ano"
OBSERVACAO = (
    "Proxy geográfico entre estações ES presentes no pacote anual. "
    "Não considera altitude ou barreiras do relevo e não comprova representatividade meteorológica. "
    "Consulte a cobertura horária dos sensores; não há imputação automática."
)
COLUNAS = (
    "codigo_ibge", "ano", "codigo_ibge_completo", "codigo_estacao",
    "latitude_municipio", "longitude_municipio", "latitude_estacao", "longitude_estacao", "altitude_estacao",
    "distancia_km", "metodo", "fonte_geografia_url", "fonte_geografia_sha256", "fonte_inmet_sha256", "observacao",
)


def hash_pontos(registros):
    pontos = [{key: row[key] for key in ("codigo_ibge_completo", "latitude", "longitude")}
              for row in sorted(registros, key=lambda row: row["codigo_ibge_completo"])]
    return hashlib.sha256(json.dumps(pontos, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def carregar_centroides(caminho=CENTROIDES, cadastro=None):
    cadastro = carregar_cadastro() if cadastro is None else cadastro
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    rows = dados["registros"]
    esperados = {row["codigo_ibge_completo"] for row in cadastro}
    if (
        dados.get("tipo") != "centroides_municipais_ibge" or len(rows) != len(esperados)
        or {row["codigo_ibge_completo"] for row in rows} != esperados
        or hash_pontos(rows) != PONTOS_SHA256 or dados.get("pontos_sha256") != PONTOS_SHA256
    ):
        raise ValueError("Snapshot de centroides diferente da referência geográfica fixada.")
    for row in rows:
        if not -90 <= row["latitude"] <= 90 or not -180 <= row["longitude"] <= 180:
            raise ValueError("Coordenadas municipais inválidas.")
        if row["fonte_url"] != f"{API_BASE}/{row['codigo_ibge_completo']}/metadados":
            raise ValueError("Fonte geográfica incompatível.")
    return rows


def baixar_centroides(caminho=CENTROIDES):
    caminho = Path(caminho)
    cadastro = carregar_cadastro()
    if caminho.is_file():
        carregar_centroides(caminho, cadastro)
        return

    def obter(row):
        codigo = row["codigo_ibge_completo"]
        url = f"{API_BASE}/{codigo}/metadados"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        metadata = response.json()
        if len(metadata) != 1 or str(metadata[0]["id"]) != codigo:
            raise ValueError("Metadados geográficos incompatíveis com o município.")
        ponto = metadata[0]["centroide"]
        return dict(codigo_ibge_completo=codigo, latitude=float(ponto["latitude"]),
                    longitude=float(ponto["longitude"]), fonte_url=url, resposta_original=metadata)

    with ThreadPoolExecutor(max_workers=3) as pool:
        registros = sorted(pool.map(obter, cadastro), key=lambda row: row["codigo_ibge_completo"])
    if hash_pontos(registros) != PONTOS_SHA256:
        raise ValueError("O IBGE alterou os pontos de referência; revise a versão antes de usar.")
    payload = dict(tipo="centroides_municipais_ibge", obtido_em_utc=datetime.now(timezone.utc).isoformat(),
                   pontos_sha256=PONTOS_SHA256, registros=registros)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def distancia_haversine(lat1, lon1, lat2, lon2):
    """Distância aproximada na superfície, adotando raio terrestre de 6.371 km."""
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(min(1, max(0, h))))


def gerar_vinculos(cadastro, pontos, resumo_clima):
    por_codigo = {row["codigo_ibge_completo"]: row for row in pontos}
    if len(por_codigo) != len(pontos) or set(por_codigo) != {row["codigo_ibge_completo"] for row in cadastro}:
        raise ValueError("Centroides sem correspondência completa com o cadastro.")
    anos = resumo_clima.get("anos_arquivos", ANOS)
    if anos not in (ANOS, ANOS_SUPORTADOS):
        raise ValueError("Período dos vínculos incompatível com os pacotes INMET conferidos.")
    disponiveis = {ano: {} for ano in anos}
    for arquivo in resumo_clima["arquivos"]:
        ano, metadata = arquivo["ano_arquivo"], arquivo["metadados"]
        codigo = metadata["codigo"]
        anterior = disponiveis[ano].get(codigo)
        if anterior and any(anterior[key] != metadata[key] for key in ("latitude", "longitude", "altitude")):
            raise ValueError("Metadados de estação ambíguos no mesmo ano.")
        disponiveis[ano][codigo] = metadata
    registros = []
    for ano in anos:
        if not disponiveis[ano]:
            raise ValueError(f"Nenhuma estação disponível no pacote anual {ano}.")
        for municipio in sorted(cadastro, key=lambda row: row["codigo_municipio"]):
            ponto = por_codigo[municipio["codigo_ibge_completo"]]
            candidatos = [(distancia_haversine(ponto["latitude"], ponto["longitude"], e["latitude"], e["longitude"]), e["codigo"], e)
                          for e in disponiveis[ano].values()]
            distancia, _, estacao = min(candidatos, key=lambda item: (item[0], item[1]))
            registros.append(dict(
                codigo_ibge=municipio["codigo_municipio"], codigo_ibge_completo=municipio["codigo_ibge_completo"],
                ano=ano, codigo_estacao=estacao["codigo"], latitude_municipio=ponto["latitude"], longitude_municipio=ponto["longitude"],
                latitude_estacao=estacao["latitude"], longitude_estacao=estacao["longitude"], altitude_estacao=estacao["altitude"],
                distancia_km=round(distancia, 3), metodo=METODO, fonte_geografia_url=ponto["fonte_url"],
                fonte_geografia_sha256=PONTOS_SHA256, fonte_inmet_sha256=resumo_clima["entrada_sha256"], observacao=OBSERVACAO,
            ))
    return registros


def validar_vinculos(registros):
    """Confere chaves, origem e consistência da distância antes de gravar no banco."""
    if not registros:
        raise ValueError("Fonte de vínculos vazia.")
    chaves = set()
    for row in registros:
        codigo, completo = row["codigo_ibge"], row["codigo_ibge_completo"]
        chave = codigo, row["ano"]
        if chave in chaves:
            raise ValueError("Vínculo municipal/ano duplicado.")
        chaves.add(chave)
        if (
            not re.fullmatch(r"32\d{4}", codigo) or not re.fullmatch(r"32\d{5}", completo)
            or completo[:6] != codigo or row["ano"] not in ANOS_SUPORTADOS
            or not re.fullmatch(r"A\d{3}", row["codigo_estacao"])
        ):
            raise ValueError("Identificadores ou ano inválidos no vínculo.")
        for campo, limite in (("latitude_municipio", 90), ("longitude_municipio", 180),
                              ("latitude_estacao", 90), ("longitude_estacao", 180)):
            valor = row[campo]
            if not isinstance(valor, (int, float)) or not math.isfinite(valor) or abs(valor) > limite:
                raise ValueError("Coordenada inválida no vínculo.")
        altitude = row["altitude_estacao"]
        if altitude is not None and (not isinstance(altitude, (int, float)) or not math.isfinite(altitude)):
            raise ValueError("Altitude inválida no vínculo.")
        calculada = round(distancia_haversine(
            row["latitude_municipio"], row["longitude_municipio"], row["latitude_estacao"], row["longitude_estacao"],
        ), 3)
        if row["distancia_km"] != calculada:
            raise ValueError("Distância incompatível com as coordenadas do vínculo.")
        if (
            row["metodo"] != METODO or row["observacao"] != OBSERVACAO
            or row["fonte_geografia_sha256"] != PONTOS_SHA256
            or not re.fullmatch(r"[0-9a-f]{64}", row["fonte_inmet_sha256"])
            or row["fonte_geografia_url"] != f"{API_BASE}/{completo}/metadados"
        ):
            raise ValueError("Método ou referência incompatível no vínculo.")


def processar_vinculos():
    carregar_clima()
    rows = gerar_vinculos(carregar_cadastro(), carregar_centroides(), json.loads(RESUMO_CLIMA.read_text(encoding="utf-8")))
    validar_vinculos(rows)
    digest = gravar_csv(OUTPUT_CSV, COLUNAS, rows)
    resumo = dict(
        schema_version=1, tipo="vinculos_municipios_estacoes", linhas_saida=len(rows), anos=sorted({r["ano"] for r in rows}),
        csv_sha256=digest, fonte_geografia_sha256=PONTOS_SHA256,
        gerado_em_utc=datetime.now(timezone.utc).isoformat(), metodo=METODO,
        distancia_maxima_km=max(row["distancia_km"] for row in rows), observacao=OBSERVACAO,
    )
    OUTPUT_JSON.write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resumo


def carregar_vinculos(caminho_csv=OUTPUT_CSV, caminho_resumo=OUTPUT_JSON):
    resumo = json.loads(Path(caminho_resumo).read_text(encoding="utf-8"))
    if (
        not isinstance(resumo, dict) or resumo.get("schema_version") != 1 or resumo.get("tipo") != "vinculos_municipios_estacoes"
        or resumo.get("csv_sha256") != sha256_arquivo(caminho_csv) or resumo.get("fonte_geografia_sha256") != PONTOS_SHA256
    ):
        raise ValueError("Vínculos e resumo incompatíveis; gere novamente a associação.")
    with Path(caminho_csv).open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or []) != COLUNAS:
            raise ValueError("Colunas dos vínculos incompatíveis.")
        rows = list(reader)
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("Quantidade inesperada de campos nos vínculos.")
        row["ano"] = int(row["ano"])
        for campo in ("latitude_municipio", "longitude_municipio", "latitude_estacao", "longitude_estacao", "altitude_estacao", "distancia_km"):
            row[campo] = float(row[campo]) if row[campo] else None
    validar_vinculos(rows)
    carregar_clima()
    expected = gerar_vinculos(carregar_cadastro(), carregar_centroides(), json.loads(RESUMO_CLIMA.read_text(encoding="utf-8")))
    if rows != expected or resumo.get("linhas_saida") != len(rows):
        raise ValueError("Os vínculos divergem do cálculo geográfico e das fontes validadas.")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baixar", action="store_true", help="Obtém e valida o snapshot de centroides oficiais, se ausente.")
    args = parser.parse_args()
    try:
        if args.baixar:
            baixar_centroides()
        resumo = processar_vinculos()
        print(json.dumps(resumo, ensure_ascii=True, indent=2))
        return 0
    except (OSError, ValueError, KeyError, requests.RequestException) as exc:
        print(f"Erro na associação de estações: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
