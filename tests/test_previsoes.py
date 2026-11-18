import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.main import app
from backend.previsoes import (
    ConsultaPrevisaoError, PrevisaoIndisponivelError, ServicoPrevisoes, carregar_servico, get_servico_previsoes,
)
from ml.preparar_dados import FEATURES, construir_proxima_semana, construir_variaveis
from tests.test_ml import base_ficticia, base_sinan_ficticia


def servico_ficticio(base=None, artefato=None, fonte="sesa"):
    base = base_ficticia(n=56, inicio=date(2023, 12, 3)) if base is None else base
    artefato = artefato or dict(nome="persistencia", familia="persistencia", parametros={}, pipeline=None)
    protocolo = dict(horizonte=1, janela=4, cobertura_minima=80)
    avaliacao = dict(
        execucao="20261118T031036125598Z_" + "a" * 16, dataset_id="a" * 16,
        selecionado={campo: artefato[campo] for campo in ("nome", "familia", "parametros")},
        validacao=[dict(nome=artefato["nome"], mae=2, rmse=3, exemplos=10)],
        teste=dict(selecionado=dict(mae=4, rmse=5, exemplos=9)),
        particoes=dict(validacao=dict(fim="2023-12-24" if fonte == "sesa" else "2024-12-22")),
    )
    return ServicoPrevisoes(artefato, avaliacao, base, dict(protocolo=protocolo, fonte=fonte))


class PrevisoesTests(unittest.TestCase):
    def test_sinan_2026_tem_periodo_e_referencia_proprios_sem_usar_metricas_sesa(self):
        servico = servico_ficticio(base_sinan_ficticia(n=100, inicio=date(2024, 12, 1)), fonte="sinan")
        resultado = servico.consultar()
        self.assertEqual(resultado.data_inicio, date(2026, 11, 1))
        self.assertEqual(resultado.modelo.fonte_serie, "sinan")
        self.assertEqual(resultado.modelo.data_referencia_registros, "DT_SIN_PRI")
        self.assertEqual(resultado.modelo.fim_historico, date(2026, 10, 31))
        self.assertEqual(resultado.modelo.ano_teste, 2025)
        self.assertIsNone(resultado.modelo.teste_2024)
        self.assertIsNone(resultado.resultados[0].registros_observados)
        self.assertEqual(servico.consultar(data_inicio=date(2026, 10, 25)).contexto, "simulacao_2026")
        self.assertEqual(servico.consultar(data_inicio=date(2025, 2, 2)).contexto, "backtest_2025")
        with self.assertRaises(ConsultaPrevisaoError):
            servico.consultar(data_inicio=date(2026, 11, 8))

    def test_inferencia_seguinte_usa_mesmas_variaveis_do_preparo_historico(self):
        base = base_ficticia(n=12, inicio=date(2023, 12, 3))
        esperado = construir_variaveis(base).iloc[[8]].reset_index(drop=True)
        obtido = construir_proxima_semana(base.iloc[:8])
        pd.testing.assert_frame_equal(esperado[FEATURES], obtido[FEATURES])
        self.assertTrue(obtido.loc[0, "elegivel_previsao"])
        self.assertFalse(obtido.loc[0, "elegivel_avaliacao"])
        self.assertTrue(pd.isna(obtido.loc[0, "alvo"]))
        self.assertTrue(pd.isna(obtido.loc[0, "populacao"]))

    def test_transicao_de_ano_53_semanas_preserva_calendario_e_lags(self):
        base = base_ficticia(n=5, inicio=date(2020, 11, 29))
        obtido = construir_proxima_semana(base).iloc[0]
        self.assertEqual(obtido["data_inicio"].date(), date(2021, 1, 3))
        self.assertEqual((obtido["ano"], obtido["semana_epidemiologica"]), (2021, 1))
        self.assertEqual(obtido["registros_lag_1"], 5)
        self.assertEqual(obtido["registros_lag_4"], 2)

    def test_consulta_padrao_e_semana_apos_snapshot_sem_inventar_alvo(self):
        resultado = servico_ficticio().consultar()
        self.assertEqual(resultado.contexto, "projecao_apos_snapshot")
        self.assertEqual(resultado.data_inicio, date(2024, 12, 29))
        self.assertEqual(resultado.data_fim, date(2025, 1, 4))
        self.assertEqual((resultado.ano, resultado.semana_epidemiologica), (2025, 1))
        self.assertEqual(resultado.data_origem, date(2024, 12, 28))
        self.assertEqual(resultado.municipios_com_previsao, 1)
        row = resultado.resultados[0]
        self.assertEqual(row.registros_previstos, row.registros_ultima_semana)
        self.assertEqual(row.registros_previstos, 56)
        self.assertIsNone(row.registros_observados)

    def test_zero_explicito_nao_se_confunde_com_falta_de_historico_ou_clima(self):
        base = base_ficticia(n=56, inicio=date(2023, 12, 3))
        base.loc[55, "registros_notificados"] = 0
        sem_registro = base.copy().assign(codigo_ibge="320520")
        sem_registro.loc[54, "registros_notificados"] = np.nan
        sem_registro.loc[54, "registro_sesa_presente"] = False
        sem_clima = base.copy().assign(codigo_ibge="320500")
        sem_clima.loc[55, "horas_precipitacao"] = 134
        original = pd.concat([base, sem_registro, sem_clima], ignore_index=True)
        copia = original.copy(deep=True)
        resultado = servico_ficticio(original).consultar()
        rows = {row.codigo_ibge: row for row in resultado.resultados}
        self.assertEqual(resultado.total_municipios, 3)
        self.assertEqual(resultado.municipios_com_previsao, 1)
        self.assertEqual(rows["320530"].registros_previstos, 0)
        self.assertEqual(rows["320530"].status, "disponivel")
        self.assertIsNone(rows["320520"].registros_previstos)
        self.assertEqual(rows["320520"].motivos, ["historico_incompleto"])
        self.assertIsNone(rows["320500"].registros_previstos)
        self.assertEqual(rows["320500"].motivos, ["clima_insuficiente"])
        pd.testing.assert_frame_equal(original, copia)

    def test_alvo_ausente_nao_impede_previsao_e_alvo_observado_nao_vaza(self):
        base = base_ficticia(n=56, inicio=date(2023, 12, 3))
        alvo = date(2024, 2, 4)
        indice = base.index[base["data_inicio"].eq(alvo)][0]
        antes = servico_ficticio(base).consultar(data_inicio=alvo).resultados[0]
        base.loc[indice, "registros_notificados"] = np.nan
        base.loc[indice, "registro_sesa_presente"] = False
        base.loc[indice, "horas_precipitacao"] = 0
        base.loc[indice, "precipitacao_mm"] = np.nan
        depois = servico_ficticio(base).consultar(data_inicio=alvo).resultados[0]
        self.assertEqual(depois.status, "disponivel")
        self.assertEqual(antes.registros_previstos, depois.registros_previstos)
        self.assertIsNone(depois.registros_observados)

    def test_datas_de_treino_dia_incorreto_e_futuro_distante_sao_recusados(self):
        servico = servico_ficticio()
        for dia in (date(2023, 12, 24), date(2024, 2, 5), date(2025, 1, 5), date(2026, 11, 22)):
            with self.subTest(dia=dia), self.assertRaises(ConsultaPrevisaoError):
                servico.consultar(data_inicio=dia)
        with self.assertRaisesRegex(ConsultaPrevisaoError, "Município"):
            servico.consultar(codigo_municipio="320999")

    def test_servico_chama_inferencia_compartilhada_para_modelo_de_arvores(self):
        class Regressor:
            def predict(self, entradas):
                return np.full(len(entradas), 12.5)

        artefato = dict(nome="floresta", familia="random_forest", parametros={}, pipeline=Regressor())
        resultado = servico_ficticio(artefato=artefato).consultar()
        self.assertEqual(resultado.resultados[0].registros_previstos, 12.5)
        self.assertEqual(resultado.modelo.familia, "random_forest")

    def test_falhas_de_artefato_e_ponteiro_nao_abrem_caminhos_externos(self):
        with tempfile.TemporaryDirectory() as folder:
            pasta = Path(folder)
            with self.assertRaises(PrevisaoIndisponivelError):
                carregar_servico(pasta, pasta)
            (pasta / "atual.json").write_text(json.dumps(dict(execucao="../fora")), encoding="utf-8")
            with patch("backend.previsoes.carregar_modelo") as carregar:
                with self.assertRaises(PrevisaoIndisponivelError):
                    carregar_servico(pasta, pasta)
                carregar.assert_not_called()

    def test_snapshot_de_outro_experimento_e_recusado_antes_de_inferir(self):
        execucao, dataset_id = "20261118T031036125598Z_" + "a" * 16, "a" * 16
        protocolo = dict(treino=[2020, 2021, 2022], validacao=[2023], teste=[2024])
        artefato = dict(schema_version=1, features=FEATURES, nome="persistencia", familia="persistencia", parametros={})
        avaliacao = dict(
            schema_version=1, execucao=execucao, dataset_id=dataset_id, protocolo=protocolo,
            selecionado={campo: artefato[campo] for campo in ("nome", "familia", "parametros")},
            base_sha256="a" * 64, exemplos_sha256="b" * 64,
        )
        resumo = dict(dataset_id=dataset_id, protocolo=protocolo, base_sha256="c" * 64, exemplos_sha256="b" * 64)
        with tempfile.TemporaryDirectory() as folder:
            pasta = Path(folder)
            (pasta / "atual.json").write_text(json.dumps(dict(execucao=execucao)), encoding="utf-8")
            with patch("backend.previsoes.carregar_modelo", return_value=(artefato, avaliacao)), \
                 patch("backend.previsoes.carregar_dataset", return_value=(None, resumo)), \
                 patch("backend.previsoes.ler_snapshot") as ler:
                with self.assertRaises(PrevisaoIndisponivelError):
                    carregar_servico(pasta, pasta)
                ler.assert_not_called()


class ApiPrevisoesTests(unittest.TestCase):
    def setUp(self):
        self.servico = servico_ficticio()
        app.dependency_overrides[get_servico_previsoes] = lambda: self.servico
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()

    def test_modelo_e_previsoes_tem_datas_versao_fonte_e_filtros(self):
        with patch("backend.database.get_engine", side_effect=AssertionError("Não deve consultar banco")):
            modelo = self.client.get("/modelo")
            self.assertEqual(modelo.status_code, 200)
            self.assertEqual(modelo.json()["familia"], "persistencia")
            self.assertEqual(modelo.json()["natureza"], "estudo_retrospectivo")
            self.assertEqual(modelo.json()["fonte_serie"], "sesa_esus_vs")
            self.assertIn("Repete a última contagem", modelo.json()["descricao_metodo"])
            resultado = self.client.get("/previsoes?data_inicio=2024-02-04&codigo_municipio=320530")
            self.assertEqual(resultado.status_code, 200)
            dados = resultado.json()
            self.assertEqual(dados["modelo"]["versao"], modelo.json()["versao"])
            self.assertEqual(dados["contexto"], "backtest_2024")
            self.assertEqual(dados["data_origem"], "2024-02-03")
            self.assertEqual(dados["total_municipios"], 1)
            self.assertEqual(dados["resultados"][0]["registros_previstos"], 9)
            self.assertEqual(self.client.get("/previsoes").json()["ano"], 2025)

    def test_datas_e_municipios_invalidos_nao_geram_previsoes(self):
        for query in ("data_inicio=2026-11-22", "data_inicio=2024-02-05", "data_inicio=invalida",
                      "codigo_municipio=310620", "codigo_municipio=3205309", "codigo_municipio=320999"):
            with self.subTest(query=query):
                self.assertEqual(self.client.get("/previsoes?" + query).status_code, 422)

    def test_sem_modelo_retorna_503_e_health_continua_funcionando(self):
        def indisponivel():
            raise PrevisaoIndisponivelError("Prepare o experimento local e reinicie a API.")

        app.dependency_overrides[get_servico_previsoes] = indisponivel
        for rota in ("/modelo", "/previsoes"):
            resposta = self.client.get(rota)
            self.assertEqual(resposta.status_code, 503)
            self.assertIn("Prepare", resposta.json()["detail"])
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_filtro_de_fonte_e_validado_e_sinan_retorna_referencia_2026(self):
        app.dependency_overrides.pop(get_servico_previsoes)
        servico = servico_ficticio(base_sinan_ficticia(n=100, inicio=date(2024, 12, 1)), fonte="sinan")
        get_servico_previsoes.cache_clear()
        try:
            with patch("backend.previsoes.carregar_servico", return_value=servico) as carregar:
                resposta = self.client.get("/previsoes?fonte=sinan")
                self.assertEqual(resposta.status_code, 200)
                self.assertEqual(resposta.json()["data_inicio"], "2026-11-01")
                carregar.assert_called_once_with(fonte="sinan")
                self.assertEqual(self.client.get("/modelo?fonte=invalida").status_code, 422)
        finally:
            get_servico_previsoes.cache_clear()


if __name__ == "__main__":
    unittest.main()
