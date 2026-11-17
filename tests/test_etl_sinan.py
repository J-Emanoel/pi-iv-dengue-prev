import contextlib
import io
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

from backend.povoar_banco import carregar_fonte
from pipelines.calendario import ano_semana_epidemiologica, semanas_no_ano
from pipelines.etl_sinan import agregar_bloco, processar_pacote


HEADER = "SG_UF,ID_MN_RESI,DT_SIN_PRI,DT_NOTIFIC,SEM_PRI,SG_UF_NOT,CLASSI_FIN\n"


class CalendarTests(unittest.TestCase):
    def test_transicoes_do_calendario_oficial(self):
        anchors = {
            "2019-12-29": (2020, 1), "2021-01-01": (2020, 53),
            "2022-01-01": (2021, 52), "2023-12-31": (2024, 1),
            "2024-12-29": (2025, 1), "2025-12-31": (2025, 53),
            "2026-01-03": (2025, 53), "2026-01-04": (2026, 1),
        }
        for value, expected in anchors.items():
            with self.subTest(value=value):
                self.assertEqual(ano_semana_epidemiologica(date.fromisoformat(value)), expected)
        self.assertEqual(semanas_no_ano(2025), 53)
        self.assertEqual(semanas_no_ano(2024), 52)


class EtlTests(unittest.TestCase):
    def test_residencia_inclui_notificado_fora_e_exclui_residente_de_fora(self):
        frame = pd.read_csv(io.StringIO(HEADER +
            "32,320530,2024-01-01,2024-01-02,202401,31,10\n"
            "31,310620,2024-01-01,2024-01-02,202401,32,10\n"
            "132,320530,2024-01-01,2024-01-02,202401,32,10\n"), dtype=str)
        totals, metrics = agregar_bloco(frame, [2024])
        self.assertEqual(dict(totals), {("320530", 2024, 1): 1})
        self.assertEqual(metrics["linhas_bruto"], 3)
        self.assertEqual(metrics["linhas_residentes_es"], 1)

    def test_usa_data_e_preserva_registros_individuais_iguais(self):
        row = "32,320530,2021-12-31,2022-01-03,202252,32,5\n"
        frame = pd.read_csv(io.StringIO(HEADER + row + row), dtype=str)
        totals, metrics = agregar_bloco(frame, [2021, 2022])
        self.assertEqual(dict(totals), {("320530", 2021, 52): 2})
        self.assertEqual(metrics["semana_origem_divergente"], 2)

    def test_rejeicoes_sao_contadas_sem_virar_zero(self):
        rows = (
            "32,320530,1987-08-23,2020-01-01,198734,32,10\n"
            "32,320530,invalid,2020-01-01,202001,32,10\n"
            "32,310620,2020-01-01,2020-01-02,202001,32,10\n"
            "32,320530,2020-01-03,2020-01-02,202001,32,10\n"
        )
        totals, metrics = agregar_bloco(pd.read_csv(io.StringIO(HEADER + rows), dtype=str), [2020])
        self.assertFalse(totals)
        self.assertEqual(metrics["fora_periodo_epidemiologico"], 1)
        self.assertEqual(metrics["municipio_invalido"], 1)
        self.assertEqual(metrics["data_invalida_ou_sintomas_apos_notificacao"], 2)

    def test_esquema_ausente_gera_erro(self):
        with self.assertRaisesRegex(ValueError, "Colunas obrigatórias"):
            agregar_bloco(pd.DataFrame({"SG_UF_NOT": ["32"]}), [2024])

    def test_periodo_preserva_dezembro_que_pertence_ao_ano_epidemiologico_seguinte(self):
        rows = (
            "32,320530,2019-12-29,2020-01-02,202001,32,10\n"
            "32,320530,2019-12-28,2020-01-02,201952,32,10\n"
        )
        totals, metrics = agregar_bloco(pd.read_csv(io.StringIO(HEADER + rows), dtype=str), [2020])
        self.assertEqual(dict(totals), {("320530", 2020, 1): 1})
        self.assertEqual(metrics["fora_periodo_epidemiologico"], 1)

    def test_pacote_em_blocos_produz_fonte_carregavel_e_unica(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            annual = io.BytesIO()
            row = "32,320530,2025-12-31,2026-01-01,202553,31,10\n"
            with zipfile.ZipFile(annual, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("DENGBR25.csv", HEADER + row * 3)
            source, output, summary = root / "source.zip", root / "out.csv", root / "out.json"
            with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("DENGBR25.csv.zip", annual.getvalue())
            original = source.read_bytes()
            with contextlib.redirect_stdout(io.StringIO()):
                document = processar_pacote(source, [2025], output, summary, chunksize=1)
            loaded = carregar_fonte(output, summary)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(document["total_registos"], 3)
            self.assertEqual(loaded.registros, [dict(
                codigo_ibge="320530", ano=2025, semana_epidemiologica=53, quantidade_casos=3,
            )])

    def test_pacote_ausente_nao_sobrescreve_saida_anterior(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output, summary = root / "source.zip", root / "out.csv", root / "out.json"
            with zipfile.ZipFile(source, "w"):
                pass
            output.write_text("previous", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Esperado um pacote"):
                processar_pacote(source, [2024], output, summary)
            self.assertEqual(output.read_text(), "previous")


if __name__ == "__main__":
    unittest.main()
