"""Gera o histórico de registros SINAN por residência e semana epidemiológica."""

import argparse
import csv
import json
import shutil
import sys
import tempfile
import warnings
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipelines.arquivos import sha256_arquivo
from pipelines.calendario import ano_semana_epidemiologica

ROOT = Path(__file__).resolve().parents[1]
ANOS_PADRAO = list(range(2020, 2027))
OUTPUT_CSV = ROOT / "data/processed/dengue_semanal.csv"
OUTPUT_JSON = ROOT / "data/processed/dengue_semanal_resumo.json"
COLUNAS = {"SG_UF", "ID_MN_RESI", "DT_SIN_PRI", "DT_NOTIFIC", "SEM_PRI"}


def normalizar_codigo(values):
    return values.str.strip().str.replace(r"\.0+$", "", regex=True)


def agregar_bloco(frame, anos):
    """Não remove linhas de pessoas iguais: a fonte não tem chave individual."""
    missing = COLUNAS - set(frame.columns)
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes: {sorted(missing)}")
    metrics = Counter(linhas_bruto=len(frame))
    resident = normalizar_codigo(frame["SG_UF"]).eq("32")
    es = frame.loc[resident].copy()
    metrics["linhas_residentes_es"] = len(es)
    codes = normalizar_codigo(es["ID_MN_RESI"])
    valid_code = codes.str.fullmatch(r"32\d{4}")
    metrics["municipio_invalido"] = int((~valid_code).sum())
    es = es.loc[valid_code].copy()
    es["codigo"] = codes.loc[valid_code]
    symptoms = pd.to_datetime(es["DT_SIN_PRI"], format="%Y-%m-%d", errors="coerce")
    notification = pd.to_datetime(es["DT_NOTIFIC"], format="%Y-%m-%d", errors="coerce")
    valid_date = symptoms.notna() & notification.notna() & symptoms.le(notification)
    metrics["data_invalida_ou_sintomas_apos_notificacao"] = int((~valid_date).sum())
    es = es.loc[valid_date].copy()
    periods = symptoms.loc[valid_date].map(lambda d: ano_semana_epidemiologica(d.date()))
    es["ano"] = periods.map(lambda p: p[0])
    es["semana"] = periods.map(lambda p: p[1])
    calculated = periods.map(lambda p: f"{p[0]}{p[1]:02d}")
    metrics["semana_origem_divergente"] = int(es["SEM_PRI"].ne(calculated).sum())
    in_period = es["ano"].isin(anos)
    metrics["fora_periodo_epidemiologico"] = int((~in_period).sum())
    es = es.loc[in_period]
    metrics["linhas_agregadas"] = len(es)
    totals = Counter({
        (str(code), int(year), int(week)): int(count)
        for (code, year, week), count in es.groupby(["codigo", "ano", "semana"]).size().items()
    })
    return totals, metrics


def localizar_zip_anual(nomes, ano):
    expected = f"DENGBR{str(ano)[-2:]}.CSV.ZIP"
    matches = [n for n in nomes if Path(n).name.upper() == expected]
    if len(matches) != 1:
        raise ValueError(f"Esperado um pacote {expected}; encontrados {len(matches)}.")
    return matches[0]


def processar_pacote(zip_path, anos, output_csv, output_json, *, chunksize=50000):
    zip_path, output_csv, output_json = map(Path, (zip_path, output_csv, output_json))
    anos = sorted(set(anos))
    if not anos or any(y < 1900 or y > 9998 for y in anos):
        raise ValueError("Informe anos válidos para o período de análise.")
    if set(anos) != set(range(min(anos), max(anos) + 1)):
        raise ValueError("O período de análise deve ter anos consecutivos.")
    if len({output_csv.resolve(), output_json.resolve(), zip_path.resolve()}) != 3:
        raise ValueError("Entrada, CSV e resumo precisam ter caminhos diferentes.")
    totals, overall, files = Counter(), Counter(), []
    source_hash = sha256_arquivo(zip_path)
    with zipfile.ZipFile(zip_path) as outer:
        packages = [(year, localizar_zip_anual(outer.namelist(), year)) for year in anos]
        for year, name in packages:
            metrics = Counter()
            print(f"Processando {name} em blocos...", flush=True)
            # Somente o ZIP comprimido usa spool; o CSV é lido diretamente em fluxo.
            with tempfile.SpooledTemporaryFile(max_size=8 * 1024**2) as spool:
                with outer.open(name) as source:
                    shutil.copyfileobj(source, spool, length=1024**2)
                spool.seek(0)
                with zipfile.ZipFile(spool) as inner:
                    candidates = [n for n in inner.namelist() if n.lower().endswith(".csv")]
                    if len(candidates) != 1:
                        raise ValueError(f"{name}: esperado exatamente um CSV.")
                    with inner.open(candidates[0]) as source, warnings.catch_warnings():
                        warnings.simplefilter("error", pd.errors.ParserWarning)
                        chunks = pd.read_csv(
                            source, sep=",", encoding="utf-8-sig", dtype=str,
                            keep_default_na=False, chunksize=chunksize,
                            on_bad_lines="error", index_col=False,
                        )
                        for frame in chunks:
                            grouped, current = agregar_bloco(frame, anos)
                            totals.update(grouped)
                            metrics.update(current)
            files.append({"ano_arquivo": year, "arquivo": name, **dict(metrics)})
            overall.update(metrics)
    if not totals:
        raise ValueError("Nenhum registro válido no período. As saídas anteriores foram preservadas.")
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    # O checksum no resumo impede carregar um par CSV/JSON de execuções diferentes.
    temporary_csv = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", suffix=".tmp",
            dir=output_csv.parent, delete=False,
        ) as target:
            temporary_csv = Path(target.name)
            writer = csv.writer(target)
            writer.writerow(["codigo_municipio", "ano_epidemiologico", "semana_epidemiologica", "registos"])
            writer.writerows((*key, value) for key, value in sorted(totals.items()))
        csv_hash = sha256_arquivo(temporary_csv)
        document = {
            "schema_version": 2,
            "projeto": "DenguePrev",
            "gerado_em_utc": datetime.now(timezone.utc).isoformat(),
            "criterio": "registros_notificados",
            "localidade": "residencia",
            "data_referencia": "DT_SIN_PRI",
            "anos_epidemiologicos": anos,
            "arquivo_entrada": zip_path.name,
            "entrada_sha256": source_hash,
            "csv_sha256": csv_hash,
            "linhas_saida": len(totals),
            "total_registos": sum(totals.values()),
            "contadores": dict(overall),
            "arquivos": files,
            "observacoes": [
                "Contagens de registros da fonte, incluindo todas as classificações.",
                "Ausência de linha não foi convertida em zero.",
                "Datas fora dos anos epidemiológicos solicitados não entram no agregado.",
                "A cobertura do SINAN no ES ainda exige conciliação com a fonte estadual.",
            ],
        }
        temporary_csv.replace(output_csv)
        output_json.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        if temporary_csv is not None:
            temporary_csv.unlink(missing_ok=True)
    print(f"Concluído: {len(totals)} linhas; {sum(totals.values())} registros.")
    print(f"CSV: {output_csv}\nResumo: {output_json}")
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "arquivos-proj-int-iv.zip")
    parser.add_argument("--years", nargs="+", type=int, default=ANOS_PADRAO)
    parser.add_argument("--output-csv", type=Path, default=OUTPUT_CSV)
    parser.add_argument("--output-json", type=Path, default=OUTPUT_JSON)
    args = parser.parse_args()
    try:
        processar_pacote(args.input, args.years, args.output_csv, args.output_json)
    except (OSError, ValueError, zipfile.BadZipFile, pd.errors.ParserError, pd.errors.ParserWarning) as exc:
        print(f"Erro no ETL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
