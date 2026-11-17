import csv
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from pipelines.etl_ibge import carregar_cadastro, ler_cadastro, processar_pacote, validar_cadastro


HEADER = "Municipios do ES\nMunic&iacute;pio [-],C&oacute;digo [-],Popula&ccedil;&atilde;o [2022],\n"


class CadastroTests(unittest.TestCase):
    def test_normaliza_nomes_codigos_e_separa_notas(self):
        source = HEADER + 'Vit&oacute;ria,3205309,322869,\n&Aacute;guia Branca,3200136,10000,\n\n<table class="fontes"><tr><td>Notas</td></tr></table>'
        rows = ler_cadastro(io.StringIO(source), quantidade_esperada=2)
        self.assertEqual([row["nome"] for row in rows], ["Águia Branca", "Vitória"])
        self.assertEqual(rows[1]["codigo_municipio"], "320530")
        self.assertEqual(rows[1]["codigo_ibge_completo"], "3205309")
        self.assertNotIn("populacao", rows[1])

    def test_cadastro_incompleto_nao_e_aceito_como_fonte_final(self):
        with self.assertRaisesRegex(ValueError, "Quantidade inesperada"):
            ler_cadastro(io.StringIO(HEADER + "Vit&oacute;ria,3205309,322869,\n"))

    def test_codigo_duplicado_ou_ambiguo_e_rejeitado(self):
        source = HEADER + "Vitoria,3205309,1,\nOutro nome,3205308,2,\n"
        with self.assertRaisesRegex(ValueError, "duplicado"):
            ler_cadastro(io.StringIO(source), quantidade_esperada=2)

    def test_codigo_fora_do_es_e_rejeitado(self):
        with self.assertRaisesRegex(ValueError, "Código municipal"):
            ler_cadastro(io.StringIO(HEADER + "Belo Horizonte,3106200,1,\n"), quantidade_esperada=1)

    def test_nome_vazio_e_correspondencia_errada_sao_rejeitados(self):
        for row in (
            dict(codigo_municipio="320530", codigo_ibge_completo="3205309", nome=""),
            dict(codigo_municipio="320530", codigo_ibge_completo="3205200", nome="Vitória"),
        ):
            with self.subTest(row=row), self.assertRaises(ValueError):
                validar_cadastro([row], quantidade_esperada=1)

    def test_cabecalho_inesperado_e_linha_truncada_sao_rejeitados(self):
        for source in ("titulo\nnome,id\nVitoria,3205309\n", HEADER + "Vitoria,3205309\n"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                ler_cadastro(io.StringIO(source), quantidade_esperada=1)


class PacoteIbgeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.zip = self.root / "originais.zip"
        self.csv = self.root / "cadastro.csv"
        self.summary = self.root / "resumo.json"
        self.manifest = self.root / "inventario.json"
        rows = "".join(f"Municipio {i},32{i:04d}0,1000,\n" for i in range(78))
        self.raw = (HEADER + rows).encode("utf-8")
        with zipfile.ZipFile(self.zip, "w") as archive:
            archive.writestr("ibge.csv", self.raw)
        self.metadata = dict(
            input=dict(sha256=hashlib.sha256(self.zip.read_bytes()).hexdigest()),
            packages=[dict(source="IBGE", filename="ibge.csv", bytes=len(self.raw),
                           sha256=hashlib.sha256(self.raw).hexdigest())],
        )
        self.manifest.write_text(json.dumps(self.metadata), encoding="utf-8")

    def tearDown(self):
        self.directory.cleanup()

    def test_gera_fonte_validada_sem_alterar_o_original(self):
        original = self.zip.read_bytes()
        summary = processar_pacote(self.zip, self.csv, self.summary, self.manifest)
        self.assertEqual(summary["linhas_saida"], 78)
        self.assertEqual(len(carregar_cadastro(self.csv, self.summary)), 78)
        self.assertEqual(self.zip.read_bytes(), original)
        with self.csv.open(encoding="utf-8", newline="") as stream:
            self.assertEqual(next(csv.reader(stream)), ["codigo_municipio", "codigo_ibge_completo", "nome"])

    def test_original_divergente_preserva_saida_anterior(self):
        self.csv.write_text("anterior", encoding="utf-8")
        self.metadata["packages"][0]["sha256"] = "0" * 64
        self.manifest.write_text(json.dumps(self.metadata), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Checksum"):
            processar_pacote(self.zip, self.csv, self.summary, self.manifest)
        self.assertEqual(self.csv.read_text(encoding="utf-8"), "anterior")

    def test_csv_alterado_nao_pode_ser_carregado(self):
        processar_pacote(self.zip, self.csv, self.summary, self.manifest)
        self.csv.write_text("alterado", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "incompatíveis"):
            carregar_cadastro(self.csv, self.summary)


if __name__ == "__main__":
    unittest.main()
