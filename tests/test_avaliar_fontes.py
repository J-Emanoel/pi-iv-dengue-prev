import codecs
import csv
import io
import json
import tempfile
import unittest
import zipfile
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backend.povoar_banco import carregar_fonte
from pipelines.arquivos import sha256_arquivo
from pipelines.avaliar_fontes import (
    ANOS, CANDIDATA_CSV, FONTES_SESA, PAGINA_SESA,
    agregar_notificacoes, baixar_fontes, carregar_serie_sesa, diagnosticar_serie,
    manifesto_sesa_sha256, processar_sesa, processar_sinan,
)
from pipelines.calendario import ano_semana_epidemiologica

CADASTRO = [dict(codigo_municipio="320530", codigo_ibge_completo="3205309")]


def frame_sesa(rows):
    return pd.DataFrame(rows, columns=["UF_PACIENTE", "IBGE_CODE_PACIENTE", "DATA_NOTIFICACAO"])


class AvaliacaoFontesTests(unittest.TestCase):
    def criar_candidata(self, pasta):
        path, report = Path(pasta) / "candidata.csv", Path(pasta) / "resumo.json"
        path.write_text("codigo_municipio,ano_epidemiologico,semana_epidemiologica,registos\n320530,2023,1,2\n320530,2024,1,3\n", encoding="utf-8")
        document = dict(
            schema_version=1, tipo="avaliacao_fontes", anos_propostos=list(ANOS),
            fonte_estadual=PAGINA_SESA, data_comparacao="data_notificacao", arquivos_sesa=list(FONTES_SESA),
            saidas_sha256={CANDIDATA_CSV.name: sha256_arquivo(path)},
            candidatos_sesa=[dict(ano=ano, combinacoes_com_registros=int(ano in (2023, 2024)),
                                 registros={2023: 2, 2024: 3}.get(ano, 0),
                                 municipios_com_registros=int(ano in (2023, 2024))) for ano in ANOS],
        )
        report.write_text(json.dumps(document), encoding="utf-8")
        return path, report

    def test_candidata_convertida_para_carga_estadual_com_versoes_e_referencia(self):
        with tempfile.TemporaryDirectory() as folder:
            csv_path, report_path = self.criar_candidata(folder)
            rows = carregar_serie_sesa(csv_path, report_path, cadastro=CADASTRO)
            self.assertEqual(len(rows), 2)
            self.assertEqual(sum(row["registros_notificados"] for row in rows), 5)
            self.assertEqual({row["data_referencia"] for row in rows}, {"DATA_NOTIFICACAO"})
            self.assertEqual(rows[0]["fonte_manifesto_sha256"], manifesto_sesa_sha256())
            self.assertEqual(rows[0]["fonte_csv_sha256"], sha256_arquivo(csv_path))

    def test_carga_estadual_rejeita_csv_alterado_e_troca_de_criterio(self):
        with tempfile.TemporaryDirectory() as folder:
            csv_path, report_path = self.criar_candidata(folder)
            original = csv_path.read_bytes()
            csv_path.write_bytes(original + b"320530,2024,2,1\n")
            with self.assertRaisesRegex(ValueError, "incompatíveis"):
                carregar_serie_sesa(csv_path, report_path, cadastro=CADASTRO)
            csv_path.write_bytes(original)
            document = json.loads(report_path.read_text(encoding="utf-8"))
            document["data_comparacao"] = "data_primeiros_sintomas"
            report_path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incompatíveis"):
                carregar_serie_sesa(csv_path, report_path, cadastro=CADASTRO)

    def test_carga_estadual_rejeita_fontes_ou_totais_divergentes(self):
        with tempfile.TemporaryDirectory() as folder:
            csv_path, report_path = self.criar_candidata(folder)
            document = json.loads(report_path.read_text(encoding="utf-8"))
            document["arquivos_sesa"][0]["sha256"] = "0" * 64
            report_path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "versão fixada"):
                carregar_serie_sesa(csv_path, report_path, cadastro=CADASTRO)
            csv_path, report_path = self.criar_candidata(folder)
            document = json.loads(report_path.read_text(encoding="utf-8"))
            document["candidatos_sesa"][-1]["registros"] = 99
            report_path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Totais estaduais"):
                carregar_serie_sesa(csv_path, report_path, cadastro=CADASTRO)

    def test_fontes_usam_residencia_e_mesma_data_com_codigos_explicitos(self):
        frame = frame_sesa([("ES", "3205309", "2023-01-01 00:00:00"), ("ES", "320530", "2023-01-02")])
        sesa, meses, metrics = agregar_notificacoes(frame, CADASTRO, "sesa")
        self.assertEqual(sesa, Counter({("320530", 2023, 1): 2}))
        self.assertEqual(meses, Counter({(2023, 1): 2}))
        self.assertEqual(metrics["codigo_residencia_invalido"], 0)
        sinan = frame.rename(columns={"UF_PACIENTE": "SG_UF", "IBGE_CODE_PACIENTE": "ID_MN_RESI", "DATA_NOTIFICACAO": "DT_NOTIFIC"})
        sinan["SG_UF"] = "32"
        self.assertEqual(agregar_notificacoes(sinan, CADASTRO, "sinan")[0], sesa)

    def test_uf_codigo_e_data_invalidos_sao_contabilizados_sem_inventar_zeros(self):
        frame = frame_sesa([
            ("ES", "3205309", "2023-01-01"), ("RJ", "3205309", "2023-01-01"),
            ("ES", "3209999", "2023-01-01"), ("ES", "3205309", "2023-02-30"),
            ("ES", "3205309", "01/02/2023"),
        ])
        rows, meses, metrics = agregar_notificacoes(frame, CADASTRO, "sesa")
        self.assertEqual(sum(rows.values()), 1)
        self.assertEqual(metrics["residentes_es"], 4)
        self.assertEqual(metrics["codigo_residencia_invalido"], 1)
        self.assertEqual(metrics["data_notificacao_invalida"], 2)
        self.assertNotIn(("320530", 2023, 2), rows)
        self.assertIsNone(meses.get((2023, 2)))

    def test_meses_calendarios_e_semanas_epidemiologicas_tem_limites_distintos(self):
        frame = frame_sesa([("ES", "3205309", "2019-12-29"), ("ES", "3205309", "2024-12-29")])
        rows, meses, metrics = agregar_notificacoes(frame, CADASTRO, "sesa")
        self.assertEqual(rows, Counter({("320530", 2020, 1): 1}))
        self.assertEqual(meses, Counter({(2024, 12): 1}))
        self.assertEqual(metrics["fora_periodo_calendario"], 1)
        self.assertEqual(metrics["fora_periodo_epidemiologico"], 1)

    def test_bloco_sem_residentes_resulta_em_contagens_vazias(self):
        rows, meses, metrics = agregar_notificacoes(frame_sesa([("RJ", "3300010", "2023-01-01")]), CADASTRO, "sesa")
        self.assertEqual(rows, {})
        self.assertEqual(meses, {})
        self.assertEqual(metrics["residentes_es"], 0)

    def test_sesa_bom_e_cp1252_ids_repetidos_preservados_e_cache_validado(self):
        with tempfile.TemporaryDirectory() as folder:
            pasta = Path(folder)
            stream = io.StringIO(newline="")
            writer = csv.writer(stream)
            writer.writerow(["NUM_NOTIFICACAO", "UF_PACIENTE", "IBGE_CODE_PACIENTE", "DATA_NOTIFICACAO", "C_CLASSIFIC"])
            writer.writerows([("id-ficticio", "ES", "3205309", "2023-01-01", "Confirmação")] * 2)
            raw = codecs.BOM_UTF8 + stream.getvalue().encode("cp1252")
            path = pasta / "fonte.csv"
            path.write_bytes(raw)
            fontes = [dict(arquivo=path.name, bytes=len(raw), sha256=sha256_arquivo(path), url="https://exemplo.invalid/fonte.csv")]
            rows, _, report = processar_sesa(CADASTRO, pasta, fontes, chunksize=1)
            self.assertEqual(sum(rows.values()), 2)
            self.assertEqual(report[0]["identificadores_repetidos"], 1)
            self.assertEqual(report[0]["classificacoes_brutas"], {"Confirmação": 2})
            self.assertEqual(path.read_bytes(), raw)
            with patch("pipelines.avaliar_fontes.requests.Session") as session:
                baixar_fontes(pasta, fontes)
                session.assert_not_called()
            path.write_bytes(raw + b"alterado")
            with self.assertRaisesRegex(ValueError, "referência fixada"):
                processar_sesa(CADASTRO, pasta, fontes)

    def test_sinan_le_todos_os_pacotes_e_nao_substitui_data_por_nome_de_ano(self):
        with tempfile.TemporaryDirectory() as folder:
            pasta = Path(folder)
            path = pasta / "originais.zip"
            with zipfile.ZipFile(path, "w") as outer:
                for ano in range(2020, 2027):
                    inner = io.BytesIO()
                    data = "2024-01-01" if ano == 2026 else f"{ano}-01-01"
                    with zipfile.ZipFile(inner, "w") as archive:
                        archive.writestr("dados.csv", "SG_UF,ID_MN_RESI,DT_NOTIFIC\n32,320530," + data + "\n")
                    outer.writestr(f"DENGBR{str(ano)[-2:]}.csv.zip", inner.getvalue())
            manifest = pasta / "inventario.json"
            manifest.write_text(json.dumps(dict(input=dict(sha256=sha256_arquivo(path)))), encoding="utf-8")
            _, meses, report = processar_sinan(CADASTRO, path, manifest, chunksize=1)
            self.assertEqual(meses[2024, 1], 2)
            self.assertNotIn((2025, 1), meses)
            self.assertEqual(len(report["arquivos"]), 7)
            manifest.write_text(json.dumps(dict(input=dict(sha256="a" * 64))), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "inventário"):
                processar_sinan(CADASTRO, path, manifest)

    def test_continuidade_exige_semanas_consecutivas_e_respeita_transicao_de_ano(self):
        rows = Counter()
        for index in range(5):
            ano, semana = ano_semana_epidemiologica(date(2022, 12, 18) + timedelta(weeks=index))
            rows["320530", ano, semana] = 0 if index == 2 else 1
        report = diagnosticar_serie(rows, {}, {}, municipios=1)
        self.assertEqual(next(r for r in report if r["ano"] == 2023)["exemplos_com_4_semanas_anteriores_e_alvo"], 1)
        del rows["320530", 2022, 52]
        report = diagnosticar_serie(rows, {}, {}, municipios=1)
        self.assertEqual(next(r for r in report if r["ano"] == 2023)["exemplos_com_4_semanas_anteriores_e_alvo"], 0)

    def test_cobertura_climatica_para_ml_usa_apenas_semanas_anteriores_ao_alvo(self):
        rows = Counter({("320530", 2023, semana): 1 for semana in range(1, 6)})
        medidas = dict(horas_previstas=168, horas_precipitacao=135, horas_temperatura=135, horas_umidade=135)
        clima = {("A612", 2023, semana): medidas for semana in range(1, 5)}
        vinculos = {("320530", 2023): "A612"}
        report = next(r for r in diagnosticar_serie(rows, clima, vinculos, 1) if r["ano"] == 2023)
        self.assertEqual(report["exemplos_com_janela_e_clima_80pct"], 1)
        # Medições futuras não suprem uma lacuna anterior, mesmo sendo completas.
        clima["A612", 2023, 1] = {**medidas, "horas_precipitacao": 134}
        clima["A612", 2023, 5] = medidas
        report = next(r for r in diagnosticar_serie(rows, clima, vinculos, 1) if r["ano"] == 2023)
        self.assertEqual(report["exemplos_com_janela_e_clima_80pct"], 0)

    def test_relatorio_candidato_nao_e_aceito_como_carga_sinan(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "candidata.csv"
            path.write_text("codigo_municipio,ano_epidemiologico,semana_epidemiologica,registos\n320530,2023,1,1\n", encoding="utf-8")
            report = Path(folder) / "avaliacao.json"
            report.write_text(json.dumps(dict(schema_version=1, tipo="avaliacao_fontes")), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incompatível"):
                carregar_fonte(path, report)


if __name__ == "__main__":
    unittest.main()
