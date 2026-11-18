"""Serve o experimento congelado, com a mesma preparação e inferência do ML."""

import json
import pickle
import re
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal

import pandas as pd

from backend.schemas import ModeloPrevisaoResponse, PrevisaoMunicipalResponse, PrevisoesResponse
from ml.preparar_dados import (
    FEATURES, construir_proxima_semana, construir_variaveis, ler_snapshot, pasta_datasets,
    protocolo_temporal, validar_base,
)
from ml.treinar import carregar_dataset, carregar_modelo, pasta_modelos, prever
from pipelines.calendario import ano_semana_epidemiologica, inicio_ano_epidemiologico


class PrevisaoIndisponivelError(RuntimeError):
    """Artefatos locais ausentes, incompatíveis ou divergentes."""


class ConsultaPrevisaoError(ValueError):
    """Data fora do estudo ou município desconhecido."""


class ServicoPrevisoes:
    def __init__(self, artefato, avaliacao, base, resumo):
        self.artefato = artefato
        self.fonte = resumo.get("fonte", "sesa")
        periodos = protocolo_temporal(self.fonte)
        self.ano_teste = periodos["teste"][0]
        protocolo = resumo["protocolo"]
        cobertura = protocolo["cobertura_minima"]
        historico = construir_variaveis(base, cobertura_minima=cobertura, fonte=self.fonte)
        proxima = construir_proxima_semana(base, cobertura_minima=cobertura, fonte=self.fonte)
        self.inicio = inicio_ano_epidemiologico(self.ano_teste)
        self.fim_historico = historico["data_inicio"].max().date()
        self.proxima = self.fim_historico + timedelta(weeks=1)
        self.exemplos = pd.concat([
            historico.loc[historico["data_inicio"].dt.date.ge(self.inicio)], proxima,
        ], ignore_index=True)
        self.codigos = set(historico["codigo_ibge"])
        escolhido = avaliacao["selecionado"]
        score = next(row for row in avaliacao["validacao"] if row["nome"] == escolhido["nome"])
        fim_desenvolvimento = date.fromisoformat(avaliacao["particoes"]["validacao"]["fim"]) + timedelta(days=6)
        if (fim_desenvolvimento >= self.inicio
                or (self.fonte == "sesa" and self.fim_historico != inicio_ano_epidemiologico(2025) - timedelta(weeks=1))
                or (self.fonte == "sinan" and ano_semana_epidemiologica(self.fim_historico)[0] != 2026)):
            raise ValueError("Calendário do artefato difere do protocolo de atendimento.")
        descricao = (
            "Repete a última contagem observada. O clima delimita a elegibilidade, mas não altera a estimativa."
            if escolhido["familia"] == "persistencia"
            else "Regressor de árvores com quatro semanas anteriores de registros e clima."
        )
        self.modelo = ModeloPrevisaoResponse(
            modelo=escolhido["nome"], familia=escolhido["familia"], descricao_metodo=descricao,
            versao=avaliacao["execucao"], dataset_id=avaliacao["dataset_id"], natureza="estudo_retrospectivo",
            fonte_serie="sesa_esus_vs" if self.fonte == "sesa" else "sinan",
            data_referencia_registros="DATA_NOTIFICACAO" if self.fonte == "sesa" else "DT_SIN_PRI",
            tipo_numerador=f"registros_notificados_{self.fonte}", horizonte_semanas=protocolo["horizonte"],
            janela_semanas=protocolo["janela"], cobertura_minima_clima_pct=cobertura,
            inicio_historico=historico["data_inicio"].min().date(), fim_historico=self.fim_historico + timedelta(days=6),
            fim_periodo_desenvolvimento=fim_desenvolvimento,
            inicio_alvos_disponiveis=self.inicio, fim_alvos_disponiveis=self.proxima,
            validacao_2023={campo: score[campo] for campo in ("mae", "rmse", "exemplos")} if self.fonte == "sesa" else None,
            teste_2024=avaliacao["teste"]["selecionado"] if self.fonte == "sesa" else None,
            ano_validacao=periodos["validacao"][0], ano_teste=self.ano_teste,
            validacao={campo: score[campo] for campo in ("mae", "rmse", "exemplos")},
            teste=avaliacao["teste"]["selecionado"],
            limitacoes=[
                f"Extração histórica de {historico['ano'].min()}–{historico['ano'].max()}; referência até {(self.fim_historico + timedelta(days=6)).isoformat()}. A projeção pode estar defasada em relação à data de consulta.",
                "O alvo inclui as classificações da fonte; registros não equivalem automaticamente a casos confirmados.",
                "Backtest com extrações revisadas; não reconstrói a disponibilidade real dos dados naquela data.",
                "Exige quatro semanas consecutivas com registros e clima qualificado; ausência não equivale a zero.",
                "Estação por proximidade e limiar horário não certificam representatividade meteorológica.",
                "MAE e RMSE descrevem a coorte avaliada, sem intervalo de confiança ou garantia por município.",
                f"A projeção seguinte ao snapshot fica fora do teste de {self.ano_teste} e não tem desempenho aferido.",
            ] + ([
                "A persistência não antecipa crescimento; a avaliação não demonstrou ganho sobre essa referência.",
            ] if escolhido["familia"] == "persistencia" else []),
        )

    def consultar(self, *, data_inicio=None, codigo_municipio=None):
        alvo = data_inicio if data_inicio is not None else self.proxima
        if alvo.weekday() != 6 or not self.inicio <= alvo <= self.proxima:
            raise ConsultaPrevisaoError(
                f"Use o domingo inicial de uma semana entre {self.inicio} e {self.proxima}. "
                "O serviço atende somente o estudo histórico e a semana seguinte ao snapshot."
            )
        if codigo_municipio is not None and codigo_municipio not in self.codigos:
            raise ConsultaPrevisaoError("Município não encontrado no snapshot da fonte selecionada.")
        parte = self.exemplos.loc[self.exemplos["data_inicio"].dt.date.eq(alvo)].copy()
        if codigo_municipio is not None:
            parte = parte.loc[parte["codigo_ibge"].eq(codigo_municipio)]
        parte = parte.sort_values("codigo_ibge")
        parte["estimado"] = float("nan")
        elegiveis = parte["elegivel_previsao"]
        if elegiveis.any():
            parte.loc[elegiveis, "estimado"] = prever(self.artefato, parte.loc[elegiveis])
        resultados = []
        for row in parte.to_dict("records"):
            motivos = []
            if not row["historico_completo"]:
                motivos.append("historico_incompleto")
            if not row["clima_qualificado"]:
                motivos.append("clima_insuficiente")
            resultados.append(PrevisaoMunicipalResponse(
                codigo_ibge=row["codigo_ibge"], nome_municipio=row["nome_municipio"],
                status="dados_insuficientes" if motivos else "disponivel", motivos=motivos,
                registros_previstos=float(row["estimado"]) if pd.notna(row["estimado"]) else None,
                registros_ultima_semana=int(row["registros_lag_1"]) if pd.notna(row["registros_lag_1"]) else None,
                registros_observados=int(row["alvo"]) if pd.notna(row["alvo"]) else None,
                historico_completo=row["historico_completo"], clima_qualificado=row["clima_qualificado"],
            ))
        ano, semana = ano_semana_epidemiologica(alvo)
        contexto = ("projecao_apos_snapshot" if alvo == self.proxima else
                    "backtest_2024" if self.fonte == "sesa" else "backtest_2025" if ano == 2025 else "simulacao_2026")
        return PrevisoesResponse(
            modelo=self.modelo, contexto=contexto,
            ano=ano, semana_epidemiologica=semana, data_inicio=alvo, data_fim=alvo + timedelta(days=6),
            data_origem=alvo - timedelta(days=1), total_municipios=len(resultados),
            municipios_com_previsao=int(elegiveis.sum()), resultados=resultados,
        )


def carregar_servico(diretorio_modelos=None, diretorio_dados=None, *, fonte="sesa"):
    """Lê apenas caminhos locais fixos; confere os vínculos entre modelo e dataset."""
    try:
        periodos = protocolo_temporal(fonte)
        modelos = pasta_modelos(fonte) if diretorio_modelos is None else Path(diretorio_modelos)
        dados = pasta_datasets(fonte) if diretorio_dados is None else Path(diretorio_dados)
        execucao = json.loads((modelos / "atual.json").read_text(encoding="utf-8"))["execucao"]
        if not isinstance(execucao, str) or not re.fullmatch(r"\d{8}T\d{12}Z_[0-9a-f]{16}", execucao):
            raise ValueError("Identificador de execução inválido.")
        artefato, avaliacao = carregar_modelo(modelos / execucao)
        dataset_id = avaliacao["dataset_id"]
        if not isinstance(dataset_id, str) or not re.fullmatch(r"[0-9a-f]{16}", dataset_id):
            raise ValueError("Identificador de dataset inválido.")
        _, resumo = carregar_dataset(dados / dataset_id)
        if (
            avaliacao.get("schema_version") != 1 or artefato.get("schema_version") != 1
            or artefato.get("features") != FEATURES or avaliacao.get("execucao") != execucao
            or resumo.get("dataset_id") != dataset_id
            or resumo.get("fonte", "sesa") != fonte or avaliacao.get("fonte", "sesa") != fonte
            or avaliacao.get("protocolo") != resumo["protocolo"]
            or any(resumo["protocolo"].get(campo) != anos for campo, anos in periodos.items())
            or any(avaliacao.get(campo) != resumo[campo] for campo in ("base_sha256", "exemplos_sha256"))
            or any(artefato.get(campo) != avaliacao["selecionado"][campo] for campo in ("nome", "familia", "parametros"))
        ):
            raise ValueError("Modelo e snapshot não pertencem ao mesmo experimento.")
        base = validar_base(ler_snapshot(dados / dataset_id / f"base_{fonte}.csv"), exigir_grade_completa=True, fonte=fonte)
        return ServicoPrevisoes(artefato, avaliacao, base, resumo)
    except (OSError, ValueError, KeyError, TypeError, StopIteration, EOFError, ImportError, pickle.UnpicklingError) as exc:
        raise PrevisaoIndisponivelError(
            f"Previsões indisponíveis: prepare os dados com python -m ml.preparar_dados --fonte {fonte}, "
            f"execute python -m ml.treinar --fonte {fonte} e reinicie a API. "
            "Modelo, snapshot e versões das dependências precisam corresponder."
        ) from exc


@lru_cache(maxsize=2)
def get_servico_previsoes(fonte: Literal["sesa", "sinan"] = "sesa"):
    # Carregamento tardio: /health e consultas ao banco funcionam sem artefatos ML.
    # Cada processo mantém o experimento congelado até o reinício da API.
    return carregar_servico(fonte=fonte)
