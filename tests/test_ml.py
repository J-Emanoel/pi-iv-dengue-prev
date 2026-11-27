import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from ml.preparar_dados import FEATURES, construir_variaveis, resumir_exemplos, validar_base
from ml.treinar import carregar_dataset, carregar_modelo, executar_experimento, metricas, prever, separar_particoes
from pipelines.arquivos import sha256_arquivo
from pipelines.calendario import ano_semana_epidemiologica


def base_ficticia(n=10, inicio=date(2022, 11, 27), codigo="320530", multiplicador=1):
    rows = []
    for index in range(n):
        dia = inicio + timedelta(weeks=index)
        ano, semana = ano_semana_epidemiologica(dia)
        rows.append(dict(
            codigo_ibge=codigo, nome_municipio="Município de teste", ano=ano, semana_epidemiologica=semana,
            data_inicio=dia, registros_notificados=multiplicador * (index + 1), registro_sesa_presente=True,
            tipo_numerador="registros_notificados_sesa", fonte_serie="sesa_esus_vs",
            data_referencia_registros="DATA_NOTIFICACAO", populacao=1000,
            horas_previstas=168, precipitacao_mm=index, temperatura_media_c=20 + index / 100,
            umidade_media_pct=60, horas_precipitacao=168, horas_temperatura=168, horas_umidade=168,
        ))
    return pd.DataFrame(rows)


CANDIDATOS_TESTE = (
    dict(nome="persistencia", familia="persistencia", parametros={}),
    dict(nome="floresta", familia="random_forest", parametros=dict(n_estimators=5, max_depth=2)),
    dict(nome="boosting", familia="gradient_boosting", parametros=dict(n_estimators=5, max_depth=2)),
)


def base_sinan_ficticia(n=235, inicio=date(2022, 1, 2)):
    base = base_ficticia(n=n, inicio=inicio).rename(columns={"registro_sesa_presente": "registro_sinan_presente"})
    base = base.drop(columns=["fonte_serie", "data_referencia_registros"])
    base["tipo_numerador"] = "registros_notificados_sinan"
    return base


class VariaveisMLTests(unittest.TestCase):
    def test_snapshot_com_coluna_individual_ou_horario_e_rejeitado(self):
        base = base_ficticia()
        base["identificador_individual"] = "ficticio"
        with self.assertRaisesRegex(ValueError, "fora do esquema agregado"):
            construir_variaveis(base)
        base = base_ficticia()
        base["data_inicio"] = pd.to_datetime(base["data_inicio"]) + np.timedelta64(12, "h")
        with self.assertRaisesRegex(ValueError, "componente horário"):
            construir_variaveis(base)

    def test_lags_por_municipio_medias_e_transicao_de_ano(self):
        frame = pd.concat([base_ficticia(), base_ficticia(codigo="320520", multiplicador=100)]).sample(frac=1, random_state=7)
        dados = construir_variaveis(frame)
        row = dados.loc[(dados["codigo_ibge"] == "320530") & (dados["data_inicio"] == "2023-01-01")].iloc[0]
        self.assertEqual(row["registros_lag_1"], 5)
        self.assertEqual(row["registros_lag_4"], 2)
        self.assertEqual(row["registros_media_4"], 3.5)
        self.assertEqual(row["chuva_media_2"], 3.5)
        self.assertTrue(row["elegivel_avaliacao"])
        self.assertEqual(row["data_origem"].date(), date(2022, 12, 31))

    def test_mudar_alvo_clima_futuro_e_populacao_nao_muda_variaveis_da_previsao(self):
        base = base_ficticia()
        antes = construir_variaveis(base)
        base.loc[7, ["registros_notificados", "populacao"]] = [9999, 90000]
        base.loc[7, ["precipitacao_mm", "temperatura_media_c", "umidade_media_pct"]] = np.nan
        base.loc[7, ["horas_precipitacao", "horas_temperatura", "horas_umidade"]] = 0
        depois = construir_variaveis(base)
        pd.testing.assert_series_equal(antes.loc[7, FEATURES], depois.loc[7, FEATURES])
        self.assertTrue(depois.loc[7, "elegivel_avaliacao"])
        self.assertNotEqual(antes.loc[7, "alvo"], depois.loc[7, "alvo"])

    def test_lacuna_nao_e_preenchida_e_lags_nao_pulam_semanas(self):
        base = base_ficticia()
        base.loc[5, "registros_notificados"] = np.nan
        base.loc[5, "registro_sesa_presente"] = False
        dados = construir_variaveis(base)
        self.assertTrue(dados.loc[5, "elegivel_previsao"])
        self.assertFalse(dados.loc[5, "elegivel_avaliacao"])
        self.assertFalse(dados.loc[8, "historico_completo"])
        sem_linha = construir_variaveis(base.drop(index=5))
        self.assertFalse(sem_linha.iloc[7]["historico_completo"])

    def test_zero_explicito_e_cobertura_exata_sao_respeitados(self):
        base = base_ficticia()
        base.loc[4, "registros_notificados"] = 0
        base.loc[4, "horas_precipitacao"] = 135
        dados = construir_variaveis(base)
        self.assertEqual(dados.loc[5, "registros_lag_1"], 0)
        self.assertTrue(dados.loc[5, "elegivel_avaliacao"])
        base.loc[4, "horas_precipitacao"] = 134
        self.assertFalse(construir_variaveis(base).loc[5, "clima_qualificado"])

    def test_dup_codigo_data_fonte_e_grade_incompleta_interrompem_preparo(self):
        base = base_ficticia()
        with self.assertRaisesRegex(ValueError, "duplicada"):
            construir_variaveis(pd.concat([base, base.iloc[:1]]))
        alterada = base.copy()
        alterada.loc[0, "data_inicio"] += timedelta(days=1)
        with self.assertRaisesRegex(ValueError, "incompatíveis"):
            construir_variaveis(alterada)
        alterada = base.copy()
        alterada["fonte_serie"] = "sinan"
        with self.assertRaisesRegex(ValueError, "sem mistura"):
            construir_variaveis(alterada)
        with self.assertRaisesRegex(ValueError, "78 municípios"):
            validar_base(base, exigir_grade_completa=True)


class ModelagemMLTests(unittest.TestCase):
    def setUp(self):
        self.dados = construir_variaveis(base_ficticia(n=130, inicio=date(2022, 1, 2)))

    def test_alteracao_de_csv_impede_treinamento_sem_resumo_correspondente(self):
        with tempfile.TemporaryDirectory() as folder:
            pasta = Path(folder)
            base_ficticia().to_csv(pasta / "base_sesa.csv", index=False)
            self.dados.to_csv(pasta / "exemplos.csv", index=False)
            resumo = dict(
                schema_version=1, tipo="dataset_ml_sesa", protocolo=dict(features=FEATURES, horizonte=1, janela=4),
                base_sha256=sha256_arquivo(pasta / "base_sesa.csv"),
                exemplos_sha256=sha256_arquivo(pasta / "exemplos.csv"), anos=resumir_exemplos(self.dados),
            )
            (pasta / "resumo.json").write_text(json.dumps(resumo), encoding="utf-8")
            dados, _ = carregar_dataset(pasta)
            self.assertEqual(len(dados), len(self.dados))
            with (pasta / "exemplos.csv").open("a", encoding="utf-8") as stream:
                stream.write("alterado\n")
            with self.assertRaisesRegex(ValueError, "incompatível ou alterado"):
                carregar_dataset(pasta)

    def test_particoes_compartilham_cortes_temporais_e_metricas_sao_conferiveis(self):
        particoes = separar_particoes(self.dados)
        self.assertLess(particoes["treino"]["data_inicio"].max(), particoes["validacao"]["data_inicio"].min())
        self.assertLess(particoes["validacao"]["data_inicio"].max(), particoes["teste"]["data_inicio"].min())
        scores = metricas([0, 2], [0, 0])
        self.assertEqual(scores["mae"], 1)
        self.assertAlmostEqual(scores["rmse"], np.sqrt(2))

    def test_alterar_rotulos_de_teste_nao_altera_escolha_ou_previsoes(self):
        _, antes, _, previsoes_antes = executar_experimento(self.dados, candidatos=CANDIDATOS_TESTE)
        alterados = self.dados.copy()
        alterados.loc[alterados["ano"] == 2024, "alvo"] *= 100
        _, depois, _, previsoes_depois = executar_experimento(alterados, candidatos=CANDIDATOS_TESTE)
        self.assertEqual(antes["selecionado"], depois["selecionado"])
        for original, alterado in zip(antes["validacao"], depois["validacao"]):
            self.assertEqual(original["nome"], alterado["nome"])
            np.testing.assert_allclose([original["mae"], original["rmse"]],
                                       [alterado["mae"], alterado["rmse"]], rtol=0, atol=1e-10)
        np.testing.assert_allclose(previsoes_antes["estimado"], previsoes_depois["estimado"])
        self.assertNotEqual(antes["teste"]["selecionado"], depois["teste"]["selecionado"])

    def test_codificacao_nao_aprende_municipio_exclusivo_do_teste(self):
        self.dados.loc[self.dados["ano"] == 2024, "codigo_ibge"] = "320999"
        artefato, report, _, _ = executar_experimento(self.dados, candidatos=CANDIDATOS_TESTE[1:2])
        categorias = artefato["pipeline"].named_steps["preprocessamento"].named_transformers_["municipio"].categories_[0]
        self.assertNotIn("320999", categorias)
        self.assertEqual(report["municipios_teste_nao_vistos_no_desenvolvimento"], ["320999"])

    def test_modelo_persistido_reproduz_previsoes_e_hash_alterado_e_rejeitado(self):
        artefato, _, _, _ = executar_experimento(self.dados, candidatos=CANDIDATOS_TESTE[1:2])
        exemplos = separar_particoes(self.dados)["teste"]
        with tempfile.TemporaryDirectory() as folder:
            pasta = Path(folder)
            joblib.dump(artefato, pasta / "modelo.joblib")
            report = dict(tipo="avaliacao_ml_sesa", modelo_sha256=sha256_arquivo(pasta / "modelo.joblib"),
                          ambiente=dict(scikit_learn=sklearn.__version__, numpy=np.__version__))
            (pasta / "avaliacao.json").write_text(json.dumps(report), encoding="utf-8")
            recarregado, _ = carregar_modelo(pasta)
            np.testing.assert_allclose(prever(artefato, exemplos), prever(recarregado, exemplos))
            with (pasta / "modelo.joblib").open("ab") as stream:
                stream.write(b"alterado")
            with self.assertRaisesRegex(ValueError, "hash divergente"):
                carregar_modelo(pasta)


class ModelagemSinanTests(unittest.TestCase):
    def test_fontes_nao_sao_intercambiaveis_silenciosamente(self):
        with self.assertRaises(ValueError):
            construir_variaveis(base_sinan_ficticia())
        with self.assertRaises(ValueError):
            construir_variaveis(base_ficticia(), fonte="sinan")

    def test_sinan_reserva_2025_e_nao_aprende_com_alvos_de_2026(self):
        dados = construir_variaveis(base_sinan_ficticia(), fonte="sinan")
        particoes = separar_particoes(dados, fonte="sinan")
        self.assertEqual(set(particoes["validacao"]["ano"]), {2024})
        self.assertEqual(set(particoes["teste"]["ano"]), {2025})
        self.assertLess(particoes["treino"]["data_inicio"].max(), particoes["validacao"]["data_inicio"].min())
        _, antes, _, previstos_antes = executar_experimento(dados, candidatos=CANDIDATOS_TESTE, fonte="sinan")
        alterados = dados.copy()
        alterados.loc[alterados["ano"].eq(2026), "alvo"] *= 10000
        _, depois, _, previstos_depois = executar_experimento(alterados, candidatos=CANDIDATOS_TESTE, fonte="sinan")
        self.assertEqual(antes["selecionado"], depois["selecionado"])
        np.testing.assert_allclose(previstos_antes["estimado"], previstos_depois["estimado"], atol=1e-10)
        for original, novo in zip(antes["validacao"], depois["validacao"]):
            np.testing.assert_allclose([original["mae"], original["rmse"]], [novo["mae"], novo["rmse"]], atol=1e-10)


if __name__ == "__main__":
    unittest.main()
