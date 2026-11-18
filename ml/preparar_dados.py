"""Congela a base estadual e prepara variáveis anteriores ao alvo, sem preencher lacunas."""

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from backend.analitica import ANOS as ANOS_SINAN, ANOS_SESA, BASE_ANALITICA, BASE_SESA
from backend.database import DatabaseConfigurationError, get_engine
from pipelines.arquivos import sha256_arquivo
from pipelines.calendario import ano_semana_epidemiologica, inicio_ano_epidemiologico, semanas_no_ano

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data/processed/ml"
JANELA = 4
HORIZONTE = 1
VARIAVEIS_CLIMA = {
    "chuva": ("precipitacao_mm", "horas_precipitacao"),
    "temperatura": ("temperatura_media_c", "horas_temperatura"),
    "umidade": ("umidade_media_pct", "horas_umidade"),
}
FEATURES_NUMERICAS = (
    [f"registros_lag_{lag}" for lag in range(1, 5)]
    + ["registros_media_2", "registros_media_4", "registros_variacao_1", "semana_sin", "semana_cos"]
    + [f"{nome}_{sufixo}" for nome in VARIAVEIS_CLIMA
       for sufixo in ([f"lag_{lag}" for lag in range(1, 5)] + ["media_2", "media_4"])]
    + [f"cobertura_{nome}_lag_{lag}" for nome in VARIAVEIS_CLIMA for lag in range(1, 5)]
)
FEATURES = ["codigo_ibge", *FEATURES_NUMERICAS]
COLUNAS_OBRIGATORIAS = {
    "codigo_ibge", "nome_municipio", "ano", "semana_epidemiologica", "data_inicio", "registros_notificados",
    "registro_sesa_presente", "tipo_numerador", "fonte_serie", "data_referencia_registros", "populacao",
    "horas_previstas", *[campo for campos in VARIAVEIS_CLIMA.values() for campo in campos],
}


def protocolo_temporal(fonte="sesa"):
    if fonte == "sesa":
        return dict(treino=[2020, 2021, 2022], validacao=[2023], teste=[2024])
    if fonte == "sinan":
        return dict(treino=[2020, 2021, 2022, 2023], validacao=[2024], teste=[2025])
    raise ValueError("Fonte ML desconhecida; use sesa ou sinan.")


def pasta_datasets(fonte="sesa"):
    protocolo_temporal(fonte)
    return OUTPUT_DIR if fonte == "sesa" else OUTPUT_DIR / "sinan"


def validar_base(base, *, exigir_grade_completa=False, fonte="sesa"):
    protocolo_temporal(fonte)
    obrigatorias = COLUNAS_OBRIGATORIAS if fonte == "sesa" else (
        COLUNAS_OBRIGATORIAS - {"registro_sesa_presente", "fonte_serie", "data_referencia_registros"}
    ) | {"registro_sinan_presente"}
    tabela = BASE_SESA if fonte == "sesa" else BASE_ANALITICA
    anos = ANOS_SESA if fonte == "sesa" else ANOS_SINAN
    if base.empty or not obrigatorias.issubset(base.columns):
        raise ValueError("Snapshot vazio ou sem as colunas da base estadual integrada.")
    if set(base.columns) - set(tabela.c.keys()):
        raise ValueError("Snapshot contém colunas fora do esquema agregado estadual.")
    frame = base.copy()
    frame["codigo_ibge"] = frame["codigo_ibge"].astype(str)
    if not frame["codigo_ibge"].str.fullmatch(r"32\d{4}").all():
        raise ValueError("Código municipal incompatível com o ES.")
    if fonte == "sesa" and not (
        frame["fonte_serie"].eq("sesa_esus_vs").all()
        and frame["data_referencia_registros"].eq("DATA_NOTIFICACAO").all()
        and frame["tipo_numerador"].eq("registros_notificados_sesa").all()
    ):
        raise ValueError("O ML requer a série SESA por data de notificação, sem mistura de fontes.")
    if fonte == "sinan" and not frame["tipo_numerador"].eq("registros_notificados_sinan").all():
        raise ValueError("O ML SINAN requer registros por primeiros sintomas, sem mistura com SESA.")
    frame["data_inicio"] = pd.to_datetime(frame["data_inicio"], format="%Y-%m-%d", errors="raise")
    if not frame["data_inicio"].eq(frame["data_inicio"].dt.normalize()).all():
        raise ValueError("O início da semana deve ser uma data sem componente horário.")
    for campo in ("ano", "semana_epidemiologica", "registros_notificados", "populacao", "horas_previstas",
                  *[campo for campos in VARIAVEIS_CLIMA.values() for campo in campos]):
        frame[campo] = pd.to_numeric(frame[campo], errors="raise")
        valores = frame[campo].dropna()
        if not np.isfinite(valores).all():
            raise ValueError(f"Valor não finito em {campo}.")
    for campo in ("ano", "semana_epidemiologica"):
        if frame[campo].isna().any() or not frame[campo].eq(np.floor(frame[campo])).all():
            raise ValueError("Ano/semana precisam ser inteiros preenchidos.")
        frame[campo] = frame[campo].astype(int)
    if not frame["ano"].isin(anos).all():
        raise ValueError(f"Snapshot fora do período validado da fonte {fonte}.")
    if frame.duplicated(["codigo_ibge", "ano", "semana_epidemiologica"]).any():
        raise ValueError("Chave municipal/semanal duplicada no snapshot.")
    for ano, semana, inicio in frame[["ano", "semana_epidemiologica", "data_inicio"]].itertuples(index=False, name=None):
        if not 1 <= semana <= semanas_no_ano(ano) or inicio.date() != (
            inicio_ano_epidemiologico(ano) + timedelta(weeks=int(semana) - 1)
        ):
            raise ValueError("Data e semana epidemiológica incompatíveis.")
    coluna_presenca = f"registro_{fonte}_presente"
    presentes = frame[coluna_presenca].map({True: True, False: False, "True": True, "False": False})
    if presentes.isna().any() or not presentes.eq(frame["registros_notificados"].notna()).all():
        raise ValueError("Presença de registros diverge dos valores nulos.")
    frame[coluna_presenca] = presentes.astype(bool)
    quantidades = frame["registros_notificados"].dropna()
    if (quantidades < 0).any() or not quantidades.eq(np.floor(quantidades)).all():
        raise ValueError("Contagens devem ser inteiros não negativos ou ausentes.")
    if (frame["populacao"].dropna() <= 0).any() or not frame["horas_previstas"].dropna().eq(168).all():
        raise ValueError("População ou contagem esperada de horas inválida.")
    for nome, (coluna, horas) in VARIAVEIS_CLIMA.items():
        validas = frame[horas]
        if ((validas < 0) | (validas > 168)).any():
            raise ValueError("Contagem de horas válidas fora da semana.")
        if (validas.gt(0) & frame[coluna].isna()).any() or (validas.eq(0) & frame[coluna].notna()).any():
            raise ValueError("Medição climática incompatível com as horas válidas.")
        if nome == "chuva" and frame[coluna].dropna().lt(0).any():
            raise ValueError("Precipitação negativa no snapshot.")
        if nome == "umidade" and not frame[coluna].dropna().between(0, 100).all():
            raise ValueError("Umidade fora dos limites no snapshot.")
    if exigir_grade_completa:
        previstas = (sum(semanas_no_ano(ano) for ano in anos) if fonte == "sesa" else
                     (frame["data_inicio"].max().date() - inicio_ano_epidemiologico(min(anos))).days // 7 + 1)
        if frame["codigo_ibge"].nunique() != 78 or not frame.groupby("codigo_ibge").size().eq(previstas).all():
            raise ValueError("O snapshot precisa conter os 78 municípios e o calendário completo do período da fonte.")
    return frame.sort_values(["codigo_ibge", "data_inicio"]).reset_index(drop=True)


def construir_variaveis(base, *, cobertura_minima=80.0, fonte="sesa"):
    return _calcular_variaveis(validar_base(base, fonte=fonte), cobertura_minima=cobertura_minima)


def construir_proxima_semana(base, *, cobertura_minima=80.0, fonte="sesa"):
    """Cria somente o alvo seguinte ao snapshot, sem inventar observações futuras."""
    frame = validar_base(base, fonte=fonte)
    proximo_inicio = frame["data_inicio"].max() + timedelta(weeks=1)
    ano, semana = ano_semana_epidemiologica(proximo_inicio.date())
    alvos = frame.groupby("codigo_ibge", sort=False).tail(1).copy()
    alvos["ano"], alvos["semana_epidemiologica"] = ano, semana
    alvos["data_inicio"] = proximo_inicio
    alvos[f"registro_{fonte}_presente"] = False
    alvos[["registros_notificados", "populacao", "horas_previstas",
           *[campo for campos in VARIAVEIS_CLIMA.values() for campo in campos]]] = np.nan
    # A linha de calendário não é uma observação e não é gravada no banco/snapshot.
    estendido = pd.concat([frame, alvos], ignore_index=True).sort_values(
        ["codigo_ibge", "data_inicio"],
    ).reset_index(drop=True)
    dados = _calcular_variaveis(estendido, cobertura_minima=cobertura_minima)
    return dados.loc[dados["data_inicio"].eq(proximo_inicio)].reset_index(drop=True)


def _calcular_variaveis(frame, *, cobertura_minima):
    """Cálculo comum ao treinamento e à inferência; recebe o histórico já validado."""
    if not np.isfinite(cobertura_minima) or not 0 <= cobertura_minima <= 100:
        raise ValueError("Cobertura climática deve estar entre 0 e 100.")
    grupos = frame.groupby("codigo_ibge", sort=False)
    resultado = frame[["codigo_ibge", "nome_municipio", "ano", "semana_epidemiologica", "data_inicio", "populacao"]].copy()
    resultado["data_origem"] = pd.to_datetime(frame["data_inicio"].to_numpy() - np.timedelta64(1, "D"))
    resultado["alvo"] = frame["registros_notificados"]
    historico = pd.Series(True, index=frame.index)
    clima = pd.Series(True, index=frame.index)
    for lag in range(1, JANELA + 1):
        anterior = grupos["data_inicio"].shift(lag)
        consecutiva = (frame["data_inicio"] - anterior).dt.days.eq(7 * lag)
        contagem = grupos["registros_notificados"].shift(lag)
        resultado[f"registros_lag_{lag}"] = contagem
        historico &= consecutiva & contagem.notna()
        previstas = grupos["horas_previstas"].shift(lag)
        for nome, (coluna, horas) in VARIAVEIS_CLIMA.items():
            valor, validas = grupos[coluna].shift(lag), grupos[horas].shift(lag)
            resultado[f"{nome}_lag_{lag}"] = valor
            resultado[f"cobertura_{nome}_lag_{lag}"] = 100 * validas / previstas.where(previstas > 0)
            clima &= consecutiva & valor.notna() & previstas.eq(168) & validas.gt(0) & validas.le(previstas)
            clima &= validas.ge(cobertura_minima * previstas / 100)
    for prefixo in ("registros", *VARIAVEIS_CLIMA):
        for janela in (2, 4):
            resultado[f"{prefixo}_media_{janela}"] = resultado[
                [f"{prefixo}_lag_{lag}" for lag in range(1, janela + 1)]
            ].mean(axis=1, skipna=False)
    resultado["registros_variacao_1"] = resultado["registros_lag_1"] - resultado["registros_lag_2"]
    fase = 2 * np.pi * (frame["semana_epidemiologica"] - 1) / frame["ano"].map(semanas_no_ano)
    resultado["semana_sin"], resultado["semana_cos"] = np.sin(fase), np.cos(fase)
    resultado["historico_completo"] = historico
    resultado["clima_qualificado"] = clima
    resultado["elegivel_previsao"] = historico & clima
    resultado["elegivel_avaliacao"] = resultado["elegivel_previsao"] & resultado["alvo"].notna()
    elegiveis = resultado.loc[resultado["elegivel_previsao"], FEATURES_NUMERICAS]
    if not np.isfinite(elegiveis.to_numpy(dtype=float)).all():
        raise ValueError("As variáveis elegíveis contêm valores ausentes ou não finitos.")
    return resultado


def resumir_exemplos(dados, *, fonte="sesa"):
    resumo = []
    protocolo = protocolo_temporal(fonte)
    for ano in (ANOS_SESA if fonte == "sesa" else ANOS_SINAN):
        rows = dados.loc[dados["ano"] == ano]
        grupo = next((nome for nome, anos in protocolo.items() if ano in anos), "aplicacao")
        resumo.append(dict(
            ano=ano, particao=grupo, combinacoes=len(rows),
            alvo_ausente=int(rows["alvo"].isna().sum()),
            alvo_observado_historico_incompleto=int((rows["alvo"].notna() & ~rows["historico_completo"]).sum()),
            alvo_observado_clima_insuficiente=int((rows["alvo"].notna() & rows["historico_completo"] & ~rows["clima_qualificado"]).sum()),
            exemplos_avaliaveis=int(rows["elegivel_avaliacao"].sum()),
            exemplos_previsao_sem_alvo=int((rows["elegivel_previsao"] & rows["alvo"].isna()).sum()),
        ))
    return resumo


def ler_snapshot(caminho):
    return pd.read_csv(caminho, dtype={"codigo_ibge": str}, float_precision="round_trip")


def extrair_snapshot(engine, *, fonte="sesa"):
    tabela = BASE_SESA if fonte == "sesa" else BASE_ANALITICA
    with engine.connect() as connection:
        if connection.dialect.name == "postgresql":
            connection = connection.execution_options(isolation_level="REPEATABLE READ")
        with connection.begin():
            if connection.dialect.name == "postgresql":
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            rows = connection.execute(select(tabela).order_by(tabela.c.codigo_ibge, tabela.c.data_inicio)).mappings().all()
    return pd.DataFrame(rows)


def preparar(*, engine=None, entrada=None, output_dir=None, cobertura_minima=80.0, fonte="sesa"):
    if (engine is None) == (entrada is None):
        raise ValueError("Informe uma conexão ou um snapshot CSV, exclusivamente.")
    output_dir = pasta_datasets(fonte) if output_dir is None else Path(output_dir)
    base = ler_snapshot(entrada) if entrada is not None else extrair_snapshot(engine, fonte=fonte)
    base = validar_base(base, fonte=fonte)
    if fonte == "sinan":
        ultima = base.loc[base["registros_notificados"].notna(), "data_inicio"].max()
        if pd.isna(ultima):
            raise ValueError("A série SINAN não tem registros observados.")
        base = base.loc[base["data_inicio"].le(ultima)].copy()
    base = validar_base(base, exigir_grade_completa=True, fonte=fonte)
    dados = construir_variaveis(base, cobertura_minima=cobertura_minima, fonte=fonte)
    snapshot = base.to_csv(index=False, date_format="%Y-%m-%d", lineterminator="\n").encode("utf-8")
    base_hash = hashlib.sha256(snapshot).hexdigest()
    exemplos = dados.to_csv(index=False, date_format="%Y-%m-%d", lineterminator="\n").encode("utf-8")
    exemplos_hash = hashlib.sha256(exemplos).hexdigest()
    protocolo = dict(versao=1, horizonte=HORIZONTE, janela=JANELA, cobertura_minima=float(cobertura_minima),
                     **protocolo_temporal(fonte), features=FEATURES)
    if fonte == "sinan":
        protocolo["fonte"] = fonte
    identificador = hashlib.sha256((base_hash + exemplos_hash + json.dumps(protocolo, sort_keys=True)).encode()).hexdigest()[:16]
    pasta = Path(output_dir) / identificador
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"base_{fonte}.csv").write_bytes(snapshot)
    (pasta / "exemplos.csv").write_bytes(exemplos)
    fontes = {campo: sorted(base[campo].dropna().astype(str).unique()) for campo in (
        "fonte_registros_manifesto_sha256", "fonte_registros_csv_sha256", "fonte_inmet_sha256",
        "fonte_geografia_sha256", "fonte_populacao_sha256",
    ) if campo in base.columns}
    resumo = dict(
        schema_version=1, tipo=f"dataset_ml_{fonte}", fonte=fonte, dataset_id=identificador,
        gerado_em_utc=datetime.now(timezone.utc).isoformat(), protocolo=protocolo,
        base_sha256=base_hash, exemplos_sha256=sha256_arquivo(pasta / "exemplos.csv"),
        ambiente=dict(pandas=pd.__version__, numpy=np.__version__),
        fontes=fontes, anos=resumir_exemplos(dados, fonte=fonte), colunas=list(dados.columns),
        observacoes=[
            f"Alvo: registros {fonte.upper()} na próxima semana, não casos confirmados. Referência: "
            + ("data de notificação." if fonte == "sesa" else "data dos primeiros sintomas."),
            "Lags, médias e cobertura climática usam somente semanas anteriores ao alvo.",
            "População do ano do alvo é metadado para normalização retrospectiva; não é variável de entrada do modelo.",
            "Semanas ausentes não foram preenchidas. Amostras completas favorecem períodos e municípios com mais registros.",
            "Backtest de extrações revisadas; a disponibilidade histórica em tempo real não foi reconstruída.",
            "O vínculo geográfico anual e o limiar de 80% não certificam representatividade meteorológica.",
        ],
    )
    (pasta / "resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    (Path(output_dir) / "atual.json").write_text(json.dumps(dict(dataset_id=identificador), indent=2) + "\n", encoding="utf-8")
    return pasta, resumo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Snapshot já extraído; sem ele, consulta o PostgreSQL configurado.")
    parser.add_argument("--cobertura-minima", type=float, default=80)
    parser.add_argument("--fonte", choices=("sesa", "sinan"), default="sesa")
    args = parser.parse_args()
    engine = None
    try:
        engine = None if args.input else get_engine()
        pasta, resumo = preparar(engine=engine, entrada=args.input, cobertura_minima=args.cobertura_minima, fonte=args.fonte)
        print(json.dumps(dict(pasta=str(pasta), anos=resumo["anos"]), ensure_ascii=True, indent=2))
        return 0
    except (SQLAlchemyError, DatabaseConfigurationError):
        print("Não foi possível consultar a base analítica. Confira conexão e preparação da visão; credenciais não são exibidas.")
    except (OSError, ValueError) as exc:
        print(f"Erro na preparação: {exc}")
    finally:
        if engine is not None:
            engine.dispose()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
