"""Compara modelos com cortes temporais próprios de cada fonte, sem misturá-las."""

import argparse
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from ml.preparar_dados import FEATURES, FEATURES_NUMERICAS, ler_snapshot, pasta_datasets, protocolo_temporal
from pipelines.arquivos import sha256_arquivo

ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "ml/models"
CANDIDATOS = (
    dict(nome="persistencia", familia="persistencia", parametros={}),
    dict(nome="random_forest_folha3", familia="random_forest",
         parametros=dict(n_estimators=200, min_samples_leaf=3, max_depth=None)),
    dict(nome="random_forest_folha5", familia="random_forest",
         parametros=dict(n_estimators=200, min_samples_leaf=5, max_depth=8)),
    dict(nome="gradient_boosting_prof2", familia="gradient_boosting",
         parametros=dict(n_estimators=150, learning_rate=0.05, max_depth=2, min_samples_leaf=3)),
    dict(nome="gradient_boosting_prof3", familia="gradient_boosting",
         parametros=dict(n_estimators=150, learning_rate=0.05, max_depth=3, min_samples_leaf=5)),
)


def separar_particoes(dados, *, fonte="sesa"):
    protocolo = protocolo_temporal(fonte)
    necessarias = {*FEATURES, "alvo", "ano", "data_inicio", "data_origem", "elegivel_avaliacao"}
    if not necessarias.issubset(dados.columns):
        raise ValueError("Dataset sem o esquema de variáveis temporais.")
    flags = dados["elegivel_avaliacao"].map({True: True, False: False, "True": True, "False": False})
    if flags.isna().any():
        raise ValueError("Elegibilidade desconhecida no dataset.")
    frame = dados.loc[flags.astype(bool)].copy()
    frame["data_inicio"] = pd.to_datetime(frame["data_inicio"], errors="raise")
    frame["data_origem"] = pd.to_datetime(frame["data_origem"], errors="raise")
    frame["codigo_ibge"] = frame["codigo_ibge"].astype(str)
    for campo in ("alvo", *FEATURES_NUMERICAS):
        frame[campo] = pd.to_numeric(frame[campo], errors="raise")
    if frame.empty or not np.isfinite(frame[["alvo", *FEATURES_NUMERICAS]].to_numpy(dtype=float)).all():
        raise ValueError("Dataset elegível vazio ou com valores não finitos.")
    if (frame["alvo"] < 0).any() or not frame["ano"].isin(range(2020, 2025 if fonte == "sesa" else 2027)).all():
        raise ValueError("Alvo ou período fora do protocolo.")
    if not (frame["data_inicio"] - frame["data_origem"]).dt.total_seconds().eq(86400).all():
        raise ValueError("Origem da previsão deve anteceder a semana do alvo.")
    particoes = {nome: frame.loc[frame["ano"].isin(anos)].sort_values(["data_inicio", "codigo_ibge"]).copy()
                 for nome, anos in protocolo.items()}
    if any(parte.empty for parte in particoes.values()):
        raise ValueError("Treino, validação e teste precisam ter exemplos elegíveis.")
    if not (particoes["treino"]["data_inicio"].max() < particoes["validacao"]["data_inicio"].min()
            and particoes["validacao"]["data_inicio"].max() < particoes["teste"]["data_inicio"].min()):
        raise ValueError("Partições se sobrepõem no calendário.")
    return particoes


def criar_pipeline(candidato):
    if candidato["familia"] == "persistencia":
        return None
    if candidato["familia"] == "random_forest":
        modelo = RandomForestRegressor(random_state=42, n_jobs=2, **candidato["parametros"])
    elif candidato["familia"] == "gradient_boosting":
        modelo = GradientBoostingRegressor(random_state=42, n_iter_no_change=None, **candidato["parametros"])
    else:
        raise ValueError("Família de modelo desconhecida.")
    transformacao = ColumnTransformer([
        ("municipio", OneHotEncoder(handle_unknown="ignore", sparse_output=False), ["codigo_ibge"]),
        ("numericas", "passthrough", FEATURES_NUMERICAS),
    ], remainder="drop")
    return Pipeline([("preprocessamento", transformacao), ("regressor", modelo)])


def prever(artefato, exemplos):
    """Inferência compartilhada pela avaliação e pelo serviço FastAPI."""
    if not set(FEATURES).issubset(exemplos.columns):
        raise ValueError("Exemplos sem todas as variáveis do modelo.")
    if not np.isfinite(exemplos[FEATURES_NUMERICAS].to_numpy(dtype=float)).all():
        raise ValueError("Exemplos de previsão contêm valores ausentes ou não finitos.")
    entradas = exemplos.loc[:, FEATURES]
    if artefato["familia"] == "persistencia":
        valores = entradas["registros_lag_1"].to_numpy(dtype=float)
    else:
        valores = artefato["pipeline"].predict(entradas)
    valores = np.maximum(np.asarray(valores, dtype=float), 0)
    if valores.shape != (len(exemplos),) or not np.isfinite(valores).all():
        raise ValueError("O modelo devolveu previsões inválidas.")
    return valores


def metricas(observado, estimado):
    return dict(mae=float(mean_absolute_error(observado, estimado)),
                rmse=float(root_mean_squared_error(observado, estimado)), exemplos=len(observado))


def tabela_previsoes(parte, estimativas, nome):
    colunas = [coluna for coluna in ("codigo_ibge", "nome_municipio", "ano", "semana_epidemiologica", "data_inicio", "data_origem") if coluna in parte]
    tabela = parte[colunas].copy()
    tabela["observado"] = parte["alvo"]
    tabela["estimado"] = estimativas
    tabela["modelo"] = nome
    if "populacao" in parte:
        denominador = pd.to_numeric(parte["populacao"], errors="raise").where(parte["populacao"] > 0)
        tabela["taxa_observada_100mil"] = 100000 * parte["alvo"] / denominador
        tabela["taxa_estimada_100mil"] = 100000 * tabela["estimado"] / denominador
    return tabela


def executar_experimento(dados, *, candidatos=CANDIDATOS, fonte="sesa"):
    particoes = separar_particoes(dados, fonte=fonte)
    treino, validacao, teste = (particoes[nome] for nome in ("treino", "validacao", "teste"))
    resultados, previsoes_validacao = [], []
    for candidato in candidatos:
        modelo = criar_pipeline(candidato)
        if modelo is not None:
            modelo.fit(treino[FEATURES], treino["alvo"])
        artefato = {**candidato, "pipeline": modelo}
        estimativas = prever(artefato, validacao)
        resultados.append({**candidato, **metricas(validacao["alvo"], estimativas)})
        previsoes_validacao.append(tabela_previsoes(validacao, estimativas, candidato["nome"]))
    # A escolha ocorre antes de qualquer acesso aos valores do alvo de teste.
    indice = min(range(len(resultados)), key=lambda i: (resultados[i]["mae"], resultados[i]["rmse"], i))
    escolhido = candidatos[indice]
    final = criar_pipeline(escolhido)
    desenvolvimento = pd.concat([treino, validacao]).sort_values(["data_inicio", "codigo_ibge"])
    if final is not None:
        final.fit(desenvolvimento[FEATURES], desenvolvimento["alvo"])
    artefato = {**escolhido, "pipeline": final, "features": FEATURES, "schema_version": 1}
    previstos = prever(artefato, teste)
    referencia = prever(dict(familia="persistencia"), teste)
    scores = dict(selecionado=metricas(teste["alvo"], previstos), persistencia=metricas(teste["alvo"], referencia))
    por_municipio = []
    previsoes_teste = tabela_previsoes(teste, previstos, escolhido["nome"])
    for codigo, grupo in previsoes_teste.groupby("codigo_ibge"):
        por_municipio.append(dict(codigo_ibge=codigo, **metricas(grupo["observado"], grupo["estimado"])))
    relatorio = dict(
        schema_version=1, tipo=f"avaliacao_ml_{fonte}", fonte=fonte, selecionado=escolhido,
        criterio=f"Menor MAE em {protocolo_temporal(fonte)['validacao'][0]}, RMSE como desempate; teste posterior não seleciona modelo.",
        validacao=resultados, teste=scores, teste_por_municipio=por_municipio,
        particoes={nome: dict(exemplos=len(parte), municipios=parte["codigo_ibge"].nunique(),
                              inicio=parte["data_inicio"].min().date().isoformat(),
                              fim=parte["data_inicio"].max().date().isoformat()) for nome, parte in particoes.items()},
        municipios_validacao_nao_vistos_no_treino=sorted(set(validacao["codigo_ibge"]) - set(treino["codigo_ibge"])),
        municipios_teste_nao_vistos_no_desenvolvimento=sorted(set(teste["codigo_ibge"]) - set(desenvolvimento["codigo_ibge"])),
        observacoes=[
            "Previsão de uma semana à frente sobre registros observados e sequências completas; não é incidência de casos confirmados.",
            "O teste usa dados anteriores observados a cada semana, sem retreinar durante o teste; não é previsão recursiva de todo o ano.",
            "Hiperparâmetros predefinidos. O selecionado é reajustado somente no treino e na validação antes do teste final.",
            "Previsões limitadas a zero inferiormente; métricas usam valores contínuos, sem arredondamento.",
            "As limitações de cobertura, clima por proximidade e extração retrospectiva acompanham as métricas.",
            "A população do ano do alvo serve somente à taxa retrospectiva apresentada; não entra no modelo.",
        ],
    )
    return artefato, relatorio, pd.concat(previsoes_validacao, ignore_index=True), previsoes_teste


def carregar_dataset(pasta):
    pasta = Path(pasta)
    resumo = json.loads((pasta / "resumo.json").read_text(encoding="utf-8"))
    fonte = resumo.get("fonte", "sesa")
    protocolo_temporal(fonte)
    if (
        resumo.get("schema_version") != 1 or resumo.get("tipo") != f"dataset_ml_{fonte}"
        or resumo.get("protocolo", {}).get("features") != FEATURES
        or resumo["protocolo"].get("horizonte") != 1 or resumo["protocolo"].get("janela") != 4
        or sha256_arquivo(pasta / f"base_{fonte}.csv") != resumo.get("base_sha256")
        or sha256_arquivo(pasta / "exemplos.csv") != resumo.get("exemplos_sha256")
        or (fonte == "sinan" and any(resumo["protocolo"].get(k) != v for k, v in protocolo_temporal(fonte).items()))
    ):
        raise ValueError("Dataset ML incompatível ou alterado; prepare novamente os exemplos.")
    dados = ler_snapshot(pasta / "exemplos.csv")
    for ano in resumo["anos"]:
        observados = dados.loc[dados["ano"] == ano["ano"], "elegivel_avaliacao"].sum()
        if int(observados) != ano["exemplos_avaliaveis"]:
            raise ValueError("Partições do CSV divergem do resumo de preparação.")
    return dados, resumo


def pasta_modelos(fonte="sesa"):
    protocolo_temporal(fonte)
    return MODELS_DIR if fonte == "sesa" else MODELS_DIR / "sinan"


def treinar(pasta_dataset, *, output_dir=None):
    dados, resumo = carregar_dataset(pasta_dataset)
    fonte = resumo.get("fonte", "sesa")
    output_dir = pasta_modelos(fonte) if output_dir is None else Path(output_dir)
    artefato, avaliacao, validacao, teste = executar_experimento(dados, fonte=fonte)
    execucao = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "_" + resumo["dataset_id"]
    pasta = Path(output_dir) / execucao
    pasta.mkdir(parents=True, exist_ok=False)
    joblib.dump(artefato, pasta / "modelo.joblib")
    validacao.to_csv(pasta / "previsoes_validacao.csv", index=False, date_format="%Y-%m-%d")
    teste.to_csv(pasta / "previsoes_teste.csv", index=False, date_format="%Y-%m-%d")
    avaliacao.update(
        execucao=execucao, dataset_id=resumo["dataset_id"], base_sha256=resumo["base_sha256"],
        exemplos_sha256=resumo["exemplos_sha256"], modelo_sha256=sha256_arquivo(pasta / "modelo.joblib"),
        protocolo=resumo["protocolo"], fontes=resumo["fontes"],
        ambiente=dict(python=platform.python_version(), scikit_learn=sklearn.__version__,
                      pandas=pd.__version__, numpy=np.__version__, joblib=joblib.__version__),
    )
    (pasta / "avaliacao.json").write_text(json.dumps(avaliacao, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Verifica a persistência usando os mesmos exemplos de teste, sem retreinar.
    recarregado, _ = carregar_modelo(pasta)
    exemplos_teste = separar_particoes(dados, fonte=fonte)["teste"]
    if not np.allclose(prever(recarregado, exemplos_teste), teste["estimado"].to_numpy(), rtol=0, atol=1e-10):
        raise ValueError("Previsões mudaram após persistir o modelo.")
    (Path(output_dir) / "atual.json").write_text(json.dumps(dict(execucao=execucao), indent=2) + "\n", encoding="utf-8")
    return pasta, avaliacao


def carregar_modelo(pasta):
    """Carrega somente artefatos locais produzidos e conferidos por este treinamento."""
    pasta = Path(pasta)
    relatorio = json.loads((pasta / "avaliacao.json").read_text(encoding="utf-8"))
    if relatorio.get("tipo") not in ("avaliacao_ml_sesa", "avaliacao_ml_sinan") or sha256_arquivo(pasta / "modelo.joblib") != relatorio.get("modelo_sha256"):
        raise ValueError("Modelo sem avaliação correspondente ou com hash divergente.")
    esperado = relatorio["ambiente"]
    if esperado["scikit_learn"] != sklearn.__version__ or esperado["numpy"] != np.__version__:
        raise ValueError("Versões do ambiente diferem das usadas no treinamento; reproduza o ambiente ou retreine.")
    return joblib.load(pasta / "modelo.joblib"), relatorio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, help="Pasta com snapshot da fonte, exemplos.csv e resumo.json.")
    parser.add_argument("--fonte", choices=("sesa", "sinan"), default="sesa", help="Seleciona o ponteiro local, sem substituir o experimento da outra fonte.")
    args = parser.parse_args()
    try:
        pasta_dataset = args.dataset
        if pasta_dataset is None:
            diretorio = pasta_datasets(args.fonte)
            atual = json.loads((diretorio / "atual.json").read_text(encoding="utf-8"))
            pasta_dataset = diretorio / atual["dataset_id"]
        pasta, avaliacao = treinar(pasta_dataset)
        print(json.dumps({"pasta": str(pasta), **{campo: avaliacao[campo] for campo in ("selecionado", "validacao", "teste", "particoes")}}, ensure_ascii=True, indent=2))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"Erro no treinamento: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
