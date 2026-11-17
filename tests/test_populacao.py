import hashlib
import io
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch
from xml.etree.ElementTree import Element, SubElement, tostring

from sqlalchemy import create_engine, event, insert, select

from backend.database import Base
from backend.models import CasoDengue, Municipio, PopulacaoMunicipal
from backend.povoar_banco import sincronizar_populacoes
from pipelines.etl_populacao import O, T, X, baixar_fontes, ler_estimativa_ods, validar_populacoes


def referencia(ano=2024, quantidade=1000):
    return dict(
        codigo_ibge="320530", codigo_ibge_completo="3205309", ano=ano,
        populacao=quantidade, data_referencia=f"{ano}-07-01", tipo="estimativa",
        fonte_url="https://ftp.ibge.gov.br/exemplo.ods", fonte_sha256="a" * 64,
        observacao="Referência sintética usada apenas no teste.",
    )


class PopulacaoSourceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.cadastro = [dict(codigo_municipio="320530", codigo_ibge_completo="3205309")]

    def tearDown(self):
        self.directory.cleanup()

    def ods(self, linhas):
        root = Element(O + "document-content")
        table = SubElement(root, T + "table")
        for valores in linhas:
            row = SubElement(table, T + "table-row")
            for value in valores:
                cell = SubElement(row, T + "table-cell")
                SubElement(cell, X + "p").text = value
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as archive:
            archive.writestr("content.xml", tostring(root))
        path = self.root / "fonte.ods"
        path.write_bytes(raw.getvalue())
        return path

    def test_ods_preserva_codigo_com_zeros_e_filtra_uf(self):
        path = self.ods([
            ["UF", "COD. UF", "COD. MUNIC", "NOME", "POPULAÇÃO ESTIMADA"],
            ["MG", "31", "06200", "Belo Horizonte", "2000000"],
            ["ES", "32", "00102", "Afonso Cláudio", "30455"],
        ])
        self.assertEqual(ler_estimativa_ods(path), {"3200102": 30455})

    def test_ods_rejeita_codigo_repetido_e_populacao_nao_positiva(self):
        header = ["UF", "COD. UF", "COD. MUNIC", "NOME", "POPULAÇÃO ESTIMADA"]
        valid = ["ES", "32", "05309", "Vitória", "1000"]
        for rows in ([header, valid, valid], [header, ["ES", "32", "05309", "Vitória", "0"]]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                ler_estimativa_ods(self.ods(rows))

    def test_serie_rejeita_lacuna_chave_repetida_e_populacao_zero(self):
        for rows in ([referencia()], [referencia(), referencia()], [referencia(quantidade=0), referencia(2025)]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                validar_populacoes(rows, self.cadastro, [2024, 2025])

    def test_relacao_2023_exige_referencia_censitaria_2022(self):
        row = referencia(2023)
        with self.assertRaisesRegex(ValueError, "censitária"):
            validar_populacoes([row], self.cadastro, [2023])
        row.update(data_referencia="2022-08-01", tipo="relacao_censitaria")
        validar_populacoes([row], self.cadastro, [2023])

    def test_download_reutiliza_copia_validada_sem_rede(self):
        path = self.root / "fonte.ods"
        path.write_bytes(b"fonte validada")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with patch("pipelines.etl_populacao.FONTES", {2024: ("fonte.ods", digest)}), patch("pipelines.etl_populacao.requests.get") as request:
            baixar_fontes(self.root)
            request.assert_not_called()

    def test_download_alterado_na_origem_preserva_arquivo_local(self):
        path = self.root / "fonte.ods"
        path.write_bytes(b"anterior")
        response = Mock(content=b"outra versao")
        with patch("pipelines.etl_populacao.FONTES", {2024: ("fonte.ods", "a" * 64)}), patch("pipelines.etl_populacao.requests.get", return_value=response):
            with self.assertRaisesRegex(ValueError, "mudou de versão"):
                baixar_fontes(self.root)
        self.assertEqual(path.read_bytes(), b"anterior")


class PopulacaoDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.directory = tempfile.TemporaryDirectory()
        with self.engine.begin() as conn:
            conn.execute(insert(Municipio.__table__), dict(codigo_ibge="320530", nome="Vitória", populacao=None))
            conn.execute(insert(CasoDengue.__table__), dict(codigo_ibge="320530", ano=2024, semana_epidemiologica=1, quantidade_casos=7))

    def tearDown(self):
        self.engine.dispose()
        self.directory.cleanup()

    def test_insere_reexecuta_atualiza_com_backup_e_preserva_casos(self):
        source = [referencia(), referencia(2025)]
        first = sincronizar_populacoes(self.engine, source, backup_dir=self.directory.name)
        self.assertEqual(first["inseridos"], 2)
        again = sincronizar_populacoes(self.engine, source, backup_dir=self.directory.name)
        self.assertEqual(again["mantidos"], 2)
        self.assertIsNone(again["backup"])
        source[0]["populacao"] = 1100
        changed = sincronizar_populacoes(self.engine, source, backup_dir=self.directory.name)
        self.assertEqual(changed["atualizados"], 1)
        self.assertTrue(Path(changed["backup"]).is_file())
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(select(CasoDengue.quantidade_casos)).scalar_one(), 7)
            self.assertIsNone(conn.execute(select(Municipio.populacao)).scalar_one())

    def test_falha_na_atualizacao_reverte_a_transacao(self):
        sincronizar_populacoes(self.engine, [referencia()], backup_dir=self.directory.name)
        def falhar(connection, cursor, statement, parameters, context, many):
            if statement.startswith("UPDATE populacoes_municipais"):
                raise RuntimeError("falha simulada")
        event.listen(self.engine, "before_cursor_execute", falhar)
        try:
            with self.assertRaisesRegex(RuntimeError, "falha simulada"):
                sincronizar_populacoes(self.engine, [referencia(quantidade=1200)], backup_dir=self.directory.name)
        finally:
            event.remove(self.engine, "before_cursor_execute", falhar)
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(select(PopulacaoMunicipal.populacao)).scalar_one(), 1000)

    def test_backup_inacessivel_impede_mudanca(self):
        sincronizar_populacoes(self.engine, [referencia()], backup_dir=self.directory.name)
        invalid = Path(self.directory.name) / "arquivo"
        invalid.write_text("arquivo", encoding="utf-8")
        with self.assertRaises(OSError):
            sincronizar_populacoes(self.engine, [referencia(quantidade=1200)], backup_dir=invalid)
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(select(PopulacaoMunicipal.populacao)).scalar_one(), 1000)

    def test_fonte_vazia_ou_municipio_desconhecido_nao_aplica(self):
        with self.assertRaisesRegex(ValueError, "vazia"):
            sincronizar_populacoes(self.engine, [])
        row = referencia()
        row.update(codigo_ibge="320520", codigo_ibge_completo="3205200")
        with self.assertRaisesRegex(ValueError, "não cadastrados"):
            sincronizar_populacoes(self.engine, [row])


if __name__ == "__main__":
    unittest.main()
