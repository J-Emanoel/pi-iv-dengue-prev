"""Contratos de leitura; executáveis com unittest e coletáveis pelo pytest."""

import io
import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.inspect_datasets import detect_encoding, inspect_csv, inspect_paths, main


SINAN = "DT_NOTIFIC,ID_MN_RESI,SEM_PRI\n2026-01-05,320530,202601\n"
INMET = (
    "REGIAO:;SE\nUF:;ES\nESTACAO:;VITÓRIA\nCODIGO (WMO):;A612\n"
    "LATITUDE:;-20,27\nLONGITUDE:;-40,30\nALTITUDE:;9\nDATA DE FUNDACAO:;31/10/06\n"
    "Data;Hora UTC;TEMPERATURA (°C);\n2020/01/01;0000 UTC;24,4;\n"
)


def profile(text, **kwargs):
    raw = text.encode("utf-8")
    return inspect_csv(io.BytesIO(raw), "sample.csv", len(raw), **kwargs)


class InspectCsvTests(unittest.TestCase):
    def test_csv_quotes_multiline_and_full_row_count(self):
        result = profile('id;nota\n1;"primeira; parte\nsegunda parte"\n2;ok\n', count_rows=True, sample_rows=1)
        self.assertEqual(result["delimiter"], ";")
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["sample_rows"], [["1", "primeira; parte\nsegunda parte"]])

    def test_sampling_does_not_read_or_claim_to_validate_later_records(self):
        result = profile("a,b\n1,2\n3,4,5\n", sample_rows=1)
        self.assertIsNone(result["row_count"])
        self.assertEqual(result["scan_mode"], "sample")
        with self.assertRaisesRegex(ValueError, "3 campos"):
            profile("a,b\n1,2\n3,4,5\n", count_rows=True)

    def test_empty_file_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "vazio"):
            profile("")

    def test_utf8_bom_and_partial_multibyte_probe(self):
        self.assertEqual(detect_encoding(b"\xef\xbb\xbfnome\nVit\xc3"), "utf-8-sig")
        result = profile("\ufeffnome\nVitória\n")
        self.assertEqual(result["columns"], ["nome"])

    def test_inmet_metadata_cp1252_and_decimal_are_preserved(self):
        raw = INMET.encode("cp1252")
        result = inspect_csv(io.BytesIO(raw), "INMET_SE_ES_A612.CSV", len(raw), count_rows=True)
        self.assertEqual(result["source"], "inmet")
        self.assertEqual(result["encoding"], "cp1252")
        self.assertEqual(result["header_line"], 9)
        self.assertEqual(result["metadata"]["CODIGO (WMO)"], "A612")
        self.assertEqual(result["sample_rows"][0][2], "24,4")
        self.assertEqual(result["empty_column_positions"], [4])
        self.assertEqual(result["row_count"], 1)

    def test_ibge_title_entities_and_footer_are_not_data(self):
        result = profile(
            'Esp&iacute;rito Santo | Todos os Munic&iacute;pios\n'
            'Munic&iacute;pio [-],C&oacute;digo [-],Popula&ccedil;&atilde;o [2022],\n'
            'Vit&oacute;ria,3205309,322869,\n\n<table class="fontes"><tr><td>IBGE, 2024</td></tr></table>',
            count_rows=True,
        )
        self.assertEqual(result["source"], "ibge")
        self.assertEqual(result["header_line"], 2)
        self.assertEqual(result["column_labels"][1], "Código [-]")
        self.assertEqual(result["columns"][1], "C&oacute;digo [-]")
        self.assertEqual(result["row_count"], 1)
        self.assertTrue(result["footer_detected"])

    def test_sinan_identified_by_real_columns_not_only_filename(self):
        self.assertEqual(profile(SINAN)["source"], "sinan")

    def test_header_only_mode_does_not_read_data_rows(self):
        result = profile("a,b\ninvalid,row,extra\n", sample_rows=0)
        self.assertEqual(result["sample_rows"], [])
        self.assertIsNone(result["row_count"])


class InspectArchiveTests(unittest.TestCase):
    def test_nested_zip_filters_weather_uf_without_filtering_sinan_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = io.BytesIO()
            with zipfile.ZipFile(nested, "w") as archive:
                archive.writestr("INMET_SE_ES_A612.CSV", INMET.encode("cp1252"))
                archive.writestr("INMET_SE_MG_A001.CSV", INMET.encode("cp1252"))
                archive.writestr("../../unsafe-path.csv", "a,b\n1,2\n")
            source = root / "original.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("2020.zip", nested.getvalue())
                archive.writestr("DENGBR26.csv", SINAN)
            result = inspect_paths([source], inmet_state="ES", count_rows=True)
            self.assertEqual(result["errors"], [])
            self.assertEqual(result["inspected_csv_count"], 3)
            self.assertEqual(result["source_counts"], {"unknown": 1, "inmet": 1, "sinan": 1})
            self.assertEqual(result["skipped_by_filter"], 1)
            self.assertEqual(list(root.iterdir()), [source])

    def test_bad_zip_is_reported_and_other_inputs_still_inspected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "broken.zip").write_bytes(b"not a ZIP")
            (root / "data.csv").write_text(SINAN, encoding="utf-8")
            result = inspect_paths([root])
            self.assertEqual(result["inspected_csv_count"], 1)
            self.assertEqual(len(result["errors"]), 1)

    def test_source_filter_and_same_input_are_not_counted_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "case.csv"
            source.write_text(SINAN, encoding="utf-8")
            result = inspect_paths([root, source], source_filter="sinan")
            self.assertEqual(result["inspected_csv_count"], 1)

    def test_cli_empty_directory_returns_nonzero_with_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "report.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main([str(root), "--output", str(output)]), 1)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["inspected_csv_count"], 0)
            self.assertEqual(len(result["errors"]), 1)

    def test_cli_refuses_to_overwrite_a_source_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "data.csv"
            source.write_text(SINAN, encoding="utf-8")
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                main([str(source), "--output", str(source)])
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(source.read_text(encoding="utf-8"), SINAN)


if __name__ == "__main__":
    unittest.main()
