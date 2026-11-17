"""Consolida estações e clima semanal do ES, preservando ausência e cobertura."""

import argparse
import csv
import hashlib
import io
import json
import math
import re
import shutil
import sys
import tempfile
import warnings
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from pipelines.arquivos import sha256_arquivo
from pipelines.calendario import ano_semana_epidemiologica, inicio_ano_epidemiologico, semanas_no_ano

ROOT = Path(__file__).resolve().parents[1]
MANIFESTO = ROOT / "docs/inventario-bases.json"
OUTPUT_DIR = ROOT / "data/processed"
ESTACOES_CSV = OUTPUT_DIR / "estacoes_inmet.csv"
CLIMA_CSV = OUTPUT_DIR / "clima_semanal_inmet.csv"
RESUMO_JSON = OUTPUT_DIR / "clima_inmet_resumo.json"
FUSO = "America/Sao_Paulo"
ANOS = list(range(2020, 2026))
COLUNAS_ESTACOES = ("codigo", "nome", "uf", "latitude", "longitude", "altitude", "ano_metadados", "fonte_sha256")
COLUNAS_CLIMA = (
    "codigo_estacao", "ano", "semana_epidemiologica", "data_inicio",
    "precipitacao_mm", "temperatura_media_c", "umidade_media_pct",
    "horas_observadas", "horas_previstas", "horas_precipitacao", "horas_temperatura", "horas_umidade",
    "inicio_utc", "fim_utc", "fuso", "fonte_sha256",
)
PREFIXOS = {
    "precipitacao": "PRECIPITAÇÃO TOTAL",
    "temperatura": "TEMPERATURA DO AR - BULBO SECO",
    "umidade": "UMIDADE RELATIVA DO AR, HORARIA",
}


def ler_arquivo(raw, ano):
    """Interpreta o CSV horário e registra medições ausentes ou inválidas."""
    text = io.TextIOWrapper(io.BytesIO(raw), encoding="cp1252", newline="")
    metadata = {}
    for _ in range(8):
        chave, separador, valor = text.readline().strip().partition(";")
        if not separador:
            raise ValueError("Metadados INMET incompletos.")
        metadata[chave.rstrip(":").strip()] = valor.strip()
    codigo = metadata.get("CODIGO (WMO)", "")
    if metadata.get("UF") != "ES" or not re.fullmatch(r"A\d{3}", codigo):
        raise ValueError("Estação fora do recorte ES ou sem código válido.")
    estacao = dict(
        codigo=codigo, nome=metadata["ESTACAO"], uf="ES", ano_metadados=ano,
        latitude=float(metadata["LATITUDE"].replace(",", ".")),
        longitude=float(metadata["LONGITUDE"].replace(",", ".")),
        altitude=float(metadata["ALTITUDE"].replace(",", ".")) if metadata.get("ALTITUDE") else None,
    )
    if not estacao["nome"] or not -90 <= estacao["latitude"] <= 90 or not -180 <= estacao["longitude"] <= 180:
        raise ValueError("Nome ou coordenadas da estação inválidos.")
    with warnings.catch_warnings():
        warnings.simplefilter("error", pd.errors.ParserWarning)
        frame = pd.read_csv(text, sep=";", dtype=str, keep_default_na=False, index_col=False, on_bad_lines="error")
    if frame.empty or not {"Data", "Hora UTC"}.issubset(frame.columns):
        raise ValueError("CSV INMET vazio ou sem data/hora.")
    horas = frame["Hora UTC"].str.strip().str.replace(r"\s*UTC$", "", regex=True)
    if not horas.str.fullmatch(r"(?:[01]\d|2[0-3])00").all():
        raise ValueError("Hora UTC fora do formato horário esperado.")
    datas = pd.to_datetime(frame["Data"], format="%Y/%m/%d", errors="raise", utc=True)
    if not datas.dt.year.eq(ano).all():
        raise ValueError("CSV INMET contém datas fora do ano do arquivo.")
    instante = datas + pd.to_timedelta(horas.str[:2].astype(int), unit="h")
    if instante.duplicated().any():
        raise ValueError("Horas duplicadas no mesmo arquivo de estação.")
    dados = pd.DataFrame({"codigo_estacao": codigo, "instante_utc": instante})
    metricas = {"horas_observadas": len(dados)}
    for campo, prefixo in PREFIXOS.items():
        colunas = [c for c in frame.columns if c.startswith(prefixo)]
        if len(colunas) != 1:
            raise ValueError(f"Coluna INMET ausente ou ambígua: {prefixo}.")
        original = frame[colunas[0]].str.strip().str.replace(",", ".", regex=False)
        numeros = pd.to_numeric(original, errors="coerce")
        ausente = original.str.upper().isin(["", "NULL", "NAN"]) | numeros.abs().eq(9999)
        invalido = ~ausente & (numeros.isna() | numeros.isin([float("inf"), -float("inf")]))
        if campo == "precipitacao":
            invalido |= ~ausente & numeros.lt(0)
        elif campo == "umidade":
            invalido |= ~ausente & ~numeros.between(0, 100)
        dados[campo] = numeros.mask(ausente | invalido)
        metricas[f"ausentes_{campo}"] = int(ausente.sum())
        metricas[f"invalidos_{campo}"] = int(invalido.sum())
    return estacao, dados, metricas


def agregar_horas(dados, fonte_hash):
    """Combina todos os arquivos antes de somar chuva e calcular médias semanais."""
    if dados.empty or dados.duplicated(["codigo_estacao", "instante_utc"]).any():
        raise ValueError("Série meteorológica vazia ou com horas de estação duplicadas.")
    dados = dados.copy()
    dias = dados["instante_utc"].dt.tz_convert(FUSO).dt.date
    calendario = {dia: ano_semana_epidemiologica(dia) for dia in dias.unique()}
    periodos = dias.map(calendario)
    dados["ano"] = periodos.map(lambda periodo: periodo[0])
    dados["semana_epidemiologica"] = periodos.map(lambda periodo: periodo[1])
    grupos = dados.groupby(["codigo_estacao", "ano", "semana_epidemiologica"])
    totais = grupos.agg(
        horas_observadas=("instante_utc", "size"), inicio_utc=("instante_utc", "min"), fim_utc=("instante_utc", "max"),
        horas_precipitacao=("precipitacao", "count"), horas_temperatura=("temperatura", "count"),
        horas_umidade=("umidade", "count"), temperatura_media_c=("temperatura", "mean"), umidade_media_pct=("umidade", "mean"),
    )
    totais["precipitacao_mm"] = grupos["precipitacao"].sum(min_count=1)
    registros = []
    for (codigo, ano, semana), row in totais.iterrows():
        inicio = inicio_ano_epidemiologico(int(ano)) + timedelta(weeks=int(semana) - 1)
        registro = dict(
            codigo_estacao=codigo, ano=int(ano), semana_epidemiologica=int(semana), data_inicio=inicio.isoformat(),
            horas_previstas=168, inicio_utc=row["inicio_utc"].isoformat(), fim_utc=row["fim_utc"].isoformat(),
            fuso=FUSO, fonte_sha256=fonte_hash,
        )
        for campo in ("horas_observadas", "horas_precipitacao", "horas_temperatura", "horas_umidade"):
            registro[campo] = int(row[campo])
        for campo in ("precipitacao_mm", "temperatura_media_c", "umidade_media_pct"):
            registro[campo] = round(float(row[campo]), 6) if pd.notna(row[campo]) else None
        registros.append(registro)
    return registros


def validar_clima(estacoes, registros):
    codigos = {row["codigo"] for row in estacoes}
    if not codigos or len(codigos) != len(estacoes) or not registros:
        raise ValueError("Estações vazias, duplicadas ou sem série semanal.")
    for row in estacoes:
        if (
            not re.fullmatch(r"A\d{3}", row["codigo"]) or row["uf"] != "ES" or not row["nome"].strip()
            or not isinstance(row["latitude"], (int, float)) or not -90 <= row["latitude"] <= 90
            or not isinstance(row["longitude"], (int, float)) or not -180 <= row["longitude"] <= 180
            or (row["altitude"] is not None and not math.isfinite(row["altitude"]))
            or row["ano_metadados"] not in ANOS or not re.fullmatch(r"[a-f0-9]{64}", row["fonte_sha256"])
        ):
            raise ValueError("Cadastro de estação inválido.")
    chaves = set()
    for row in registros:
        codigo, ano, semana = row["codigo_estacao"], row["ano"], row["semana_epidemiologica"]
        chave = codigo, ano, semana
        if codigo not in codigos or chave in chaves or ano not in ANOS or not 1 <= semana <= semanas_no_ano(ano):
            raise ValueError("Chave climática inválida ou duplicada.")
        inicio = inicio_ano_epidemiologico(ano) + timedelta(weeks=semana - 1)
        if date.fromisoformat(row["data_inicio"]) != inicio or row["fuso"] != FUSO:
            raise ValueError("Início de semana ou fuso incompatível.")
        horas = row["horas_observadas"]
        if type(horas) is not int or not 1 <= horas <= 168 or row["horas_previstas"] != 168:
            raise ValueError("Contagem de horas incompatível com a semana.")
        limites = [datetime.fromisoformat(row[campo]) for campo in ("inicio_utc", "fim_utc")]
        for instante in limites:
            if instante.utcoffset() != timedelta(0) or instante.minute or instante.second:
                raise ValueError("Limites horários precisam estar em UTC.")
            dia_local = pd.Timestamp(instante).tz_convert(FUSO).date()
            if ano_semana_epidemiologica(dia_local) != (ano, semana):
                raise ValueError("Limite UTC fora da semana epidemiológica declarada.")
        if limites[0] > limites[1] or horas > (limites[1] - limites[0]).total_seconds() / 3600 + 1:
            raise ValueError("Quantidade de horas diverge do intervalo observado.")
        for campo, contagem in (("precipitacao_mm", "horas_precipitacao"), ("temperatura_media_c", "horas_temperatura"), ("umidade_media_pct", "horas_umidade")):
            valor, validas = row[campo], row[contagem]
            if type(validas) is not int or not 0 <= validas <= horas or ((valor is None) != (validas == 0)):
                raise ValueError("Valor climático não corresponde à cobertura de horas válidas.")
            if valor is not None and (not math.isfinite(valor) or (campo == "precipitacao_mm" and valor < 0) or (campo == "umidade_media_pct" and not 0 <= valor <= 100)):
                raise ValueError("Medição climática fora dos limites aceitos.")
        if not re.fullmatch(r"[a-f0-9]{64}", row["fonte_sha256"]):
            raise ValueError("Checksum de origem climática inválido.")
        chaves.add(chave)


def gravar_csv(caminho, colunas, registros):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=caminho.parent, delete=False) as stream:
            temporario = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=colunas)
            writer.writeheader()
            writer.writerows(registros)
        digest = sha256_arquivo(temporario)
        temporario.replace(caminho)
        return digest
    finally:
        if temporario is not None:
            temporario.unlink(missing_ok=True)


def processar_pacote(zip_path=ROOT / "arquivos-proj-int-iv.zip", output_dir=OUTPUT_DIR, manifesto=MANIFESTO):
    zip_path, output_dir, manifesto = Path(zip_path), Path(output_dir), Path(manifesto)
    saidas = [output_dir / name for name in (ESTACOES_CSV.name, CLIMA_CSV.name, RESUMO_JSON.name)]
    if {path.resolve() for path in saidas} & {zip_path.resolve(), manifesto.resolve()}:
        raise ValueError("Saídas não podem sobrescrever os originais ou o manifesto.")
    inventario = json.loads(manifesto.read_text(encoding="utf-8"))
    digest = sha256_arquivo(zip_path)
    if digest != inventario["input"]["sha256"]:
        raise ValueError("ZIP diferente do inventário de originais.")
    fontes = {item["filename"]: item for item in inventario["packages"] if item["source"].startswith("INMET")}
    estacoes, frames, arquivos = {}, [], []
    with zipfile.ZipFile(zip_path) as outer:
        for ano in ANOS:
            nome = f"{ano}.zip"
            fonte = fontes[nome]
            candidatos = [item for item in outer.infolist() if Path(item.filename).name == nome]
            if len(candidatos) != 1 or candidatos[0].file_size != fonte["bytes"]:
                raise ValueError(f"Pacote anual {ano} ausente ou ambíguo.")
            print(f"Processando estações ES do pacote {ano}...", flush=True)
            with tempfile.SpooledTemporaryFile(max_size=8 * 1024**2) as spool:
                with outer.open(candidatos[0]) as source:
                    shutil.copyfileobj(source, spool, length=1024**2)
                spool.seek(0)
                anual_hash = hashlib.sha256()
                for bloco in iter(lambda: spool.read(1024**2), b""):
                    anual_hash.update(bloco)
                if anual_hash.hexdigest() != fonte["sha256"]:
                    raise ValueError(f"Checksum do pacote {ano} diverge do inventário.")
                spool.seek(0)
                with zipfile.ZipFile(spool) as inner:
                    membros = [item for item in inner.infolist() if "INMET_SE_ES_" in item.filename.upper() and item.filename.lower().endswith(".csv")]
                    if len(membros) != fonte["es_weather_csv_count"]:
                        raise ValueError(f"Quantidade de arquivos ES diverge no pacote {ano}.")
                    for membro in membros:
                        raw = inner.read(membro)
                        estacao, dados, metricas = ler_arquivo(raw, ano)
                        if f"_ES_{estacao['codigo']}_" not in membro.filename.upper():
                            raise ValueError("Código da estação diverge do nome do arquivo.")
                        estacoes[estacao["codigo"]] = {**estacao, "fonte_sha256": digest}
                        frames.append(dados)
                        arquivos.append(dict(ano_arquivo=ano, arquivo=membro.filename, sha256=hashlib.sha256(raw).hexdigest(), metadados=estacao, **metricas))
    dados = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    semanas = agregar_horas(dados, digest)
    cadastro = sorted(estacoes.values(), key=lambda row: row["codigo"])
    validar_clima(cadastro, semanas)
    resumo = dict(
        schema_version=1, tipo="clima_semanal_inmet", fuso=FUSO, anos_arquivos=ANOS,
        gerado_em_utc=datetime.now(timezone.utc).isoformat(), entrada_sha256=digest,
        estacoes=len(cadastro), linhas_saida=len(semanas), horas_observadas=len(dados), arquivos=arquivos,
        estacoes_sha256=gravar_csv(saidas[0], COLUNAS_ESTACOES, cadastro),
        clima_sha256=gravar_csv(saidas[1], COLUNAS_CLIMA, semanas),
        observacoes=[
            "Semanas de domingo a sábado calculadas no fuso America/Sao_Paulo.",
            "Chuva é a soma das horas válidas; médias usam apenas medições válidas. Consulte a cobertura.",
            "Valores ausentes não foram convertidos em zero; não houve imputação.",
            "Metadados do cadastro usam o último arquivo disponível; versões anuais estão neste resumo.",
            "Não há clima de 2026 neste pacote. Vínculos geográficos são gerados separadamente por pipelines.vincular_estacoes.",
        ],
    )
    saidas[2].write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resumo


def carregar_clima(caminho_csv=CLIMA_CSV, caminho_resumo=RESUMO_JSON, caminho_estacoes=ESTACOES_CSV):
    resumo = json.loads(Path(caminho_resumo).read_text(encoding="utf-8"))
    if (
        not isinstance(resumo, dict) or resumo.get("schema_version") != 1 or resumo.get("tipo") != "clima_semanal_inmet"
        or resumo.get("fuso") != FUSO or resumo.get("anos_arquivos") != ANOS
        or resumo.get("clima_sha256") != sha256_arquivo(caminho_csv)
        or resumo.get("estacoes_sha256") != sha256_arquivo(caminho_estacoes)
    ):
        raise ValueError("Arquivos de clima incompatíveis; gere novamente o ETL INMET.")
    def ler_csv(path, colunas):
        with Path(path).open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or []) != colunas:
                raise ValueError("Colunas meteorológicas incompatíveis.")
            rows = list(reader)
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise ValueError("Quantidade de campos meteorológicos inválida.")
        return rows
    estacoes = ler_csv(caminho_estacoes, COLUNAS_ESTACOES)
    semanas = ler_csv(caminho_csv, COLUNAS_CLIMA)
    for row in estacoes:
        for campo in ("latitude", "longitude", "altitude"):
            row[campo] = float(row[campo]) if row[campo] else None
        row["ano_metadados"] = int(row["ano_metadados"])
    for row in semanas:
        for campo in ("ano", "semana_epidemiologica", "horas_observadas", "horas_previstas", "horas_precipitacao", "horas_temperatura", "horas_umidade"):
            row[campo] = int(row[campo])
        for campo in ("precipitacao_mm", "temperatura_media_c", "umidade_media_pct"):
            row[campo] = float(row[campo]) if row[campo] else None
    validar_clima(estacoes, semanas)
    if (
        len(estacoes) != resumo["estacoes"] or len(semanas) != resumo["linhas_saida"]
        or sum(row["horas_observadas"] for row in semanas) != resumo["horas_observadas"]
        or any(row["fonte_sha256"] != resumo["entrada_sha256"] for row in estacoes + semanas)
    ):
        raise ValueError("Totais ou origem do clima divergem do resumo.")
    return estacoes, semanas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "arquivos-proj-int-iv.zip")
    args = parser.parse_args()
    try:
        resumo = processar_pacote(args.input)
        print(f"INMET validado: {resumo['estacoes']} estações; {resumo['linhas_saida']} semanas; {resumo['horas_observadas']} horas.")
        return 0
    except (OSError, ValueError, KeyError, csv.Error, zipfile.BadZipFile, pd.errors.ParserError, pd.errors.ParserWarning) as exc:
        print(f"Erro no ETL INMET: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
