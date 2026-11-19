import csv
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch, sentinel

from sqlalchemy import create_engine, event, insert, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend import povoar_banco
from backend.models import CasoDengue, Municipio
from backend.povoar_banco import FonteCarga, carregar_fonte, sincronizar_casos, sincronizar_municipios


def record(week=1, quantity=7, year=2024):
    return dict(codigo_ibge="320530", ano=year, semana_epidemiologica=week, quantidade_casos=quantity)


class DatabaseLoadingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.engine = create_engine("sqlite://")
        # Representa exatamente a tabela antiga, sem índice de unicidade.
        with self.engine.begin() as connection:
            Municipio.__table__.create(connection)
            connection.execute(text(
                "CREATE TABLE casos_dengue (id INTEGER PRIMARY KEY, codigo_ibge VARCHAR, "
                "ano INTEGER NOT NULL, semana_epidemiologica INTEGER NOT NULL, quantidade_casos INTEGER)"
            ))
            connection.execute(insert(Municipio.__table__), [dict(
                codigo_ibge="320530", nome="Vitória", populacao=322869,
            )])

    def tearDown(self):
        self.engine.dispose()
        self.directory.cleanup()

    def seed(self, records):
        with self.engine.begin() as connection:
            connection.execute(insert(CasoDengue.__table__), records)

    def rows(self):
        with self.engine.connect() as connection:
            return [dict(r) for r in connection.execute(select(CasoDengue.__table__)).mappings()]

    def test_corrige_duplicados_sem_somar_e_reexecuta_sem_mudar_ids(self):
        self.seed([record(), record(), record()])
        source = FonteCarga([record()], [2024])
        first = sincronizar_casos(self.engine, source, backup_dir=self.root)
        self.assertEqual(first["duplicados_removidos"], 2)
        self.assertEqual(first["registos_no_periodo"], 7)
        self.assertTrue(Path(first["backup"]).is_file())
        with Path(first["backup"]).open(encoding="utf-8", newline="") as stream:
            backup = list(csv.DictReader(stream))
        self.assertEqual(len(backup), 3)
        self.assertEqual(sum(int(row["quantidade_casos"]) for row in backup), 21)
        original_rows = self.rows()
        second = sincronizar_casos(self.engine, source, backup_dir=self.root)
        self.assertEqual(self.rows(), original_rows)
        self.assertEqual(second["inseridos"], 0)
        self.assertEqual(second["atualizados"], 0)
        self.assertEqual(second["duplicados_removidos"], 0)
        self.assertIsNone(second["backup"])
        with self.engine.connect() as connection:
            city = connection.execute(select(Municipio.__table__)).mappings().one()
            self.assertEqual(city["nome"], "Vitória")
            self.assertEqual(city["populacao"], 322869)

    def test_indice_impede_duplicacao_por_outro_script(self):
        sincronizar_casos(self.engine, FonteCarga([record()], [2024]), backup_dir=self.root)
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(insert(CasoDengue.__table__), record())
        self.assertEqual(len(self.rows()), 1)

    def test_banco_vazio_cria_tabelas_e_cadastra_municipio(self):
        fresh_engine = create_engine("sqlite://")
        try:
            result = sincronizar_casos(
                fresh_engine, FonteCarga([record()], [2024]), backup_dir=self.root,
            )
            self.assertEqual(result["municipios_inseridos"], 1)
            self.assertEqual(result["inseridos"], 1)
            self.assertEqual(result["registos_no_periodo"], 7)
            self.assertIsNone(result["backup"])
        finally:
            fresh_engine.dispose()

    def test_atualiza_fonte_remove_obsoleto_e_preserva_outros_anos(self):
        self.seed([record(quantity=99), record(week=2), record(year=2023)])
        result = sincronizar_casos(
            self.engine, FonteCarga([record(quantity=8), record(week=3)], [2024]), backup_dir=self.root,
        )
        self.assertEqual(result["atualizados"], 1)
        self.assertEqual(result["fora_da_fonte_removidos"], 1)
        self.assertEqual(result["inseridos"], 1)
        self.assertEqual(result["registos_no_periodo"], 15)
        self.assertEqual(len([r for r in self.rows() if r["ano"] == 2023]), 1)

    def test_falha_no_indice_reverte_toda_a_correcao(self):
        self.seed([record(quantity=99), record(quantity=99)])
        original = self.rows()

        def fail_index(connection, cursor, statement, parameters, context, many):
            if statement.upper().startswith("CREATE UNIQUE INDEX"):
                raise RuntimeError("failure injected during index creation")

        event.listen(self.engine, "before_cursor_execute", fail_index)
        try:
            with self.assertRaisesRegex(RuntimeError, "failure injected"):
                sincronizar_casos(self.engine, FonteCarga([record()], [2024]), backup_dir=self.root)
        finally:
            event.remove(self.engine, "before_cursor_execute", fail_index)
        self.assertEqual(self.rows(), original)

    def test_backup_inacessivel_impede_alteracao(self):
        self.seed([record(), record()])
        original = self.rows()
        target = self.root / "not_a_directory"
        target.write_text("file", encoding="utf-8")
        with self.assertRaises(OSError):
            sincronizar_casos(self.engine, FonteCarga([record()], [2024]), backup_dir=target)
        self.assertEqual(self.rows(), original)

    def test_duplicados_fora_do_periodo_nao_sao_apagados_por_suposição(self):
        self.seed([record(year=2023), record(year=2023)])
        original = self.rows()
        with self.assertRaisesRegex(ValueError, "fora da fonte"):
            sincronizar_casos(self.engine, FonteCarga([record()], [2024]), backup_dir=self.root)
        self.assertEqual(self.rows(), original)

    def cadastro(self):
        return [dict(codigo_municipio="320530", codigo_ibge_completo="3205309", nome="Vitória")]

    def test_cadastro_altera_apenas_nome_e_preserva_casos_populacao_e_ids(self):
        self.seed([record(), record(year=2023)])
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE municipios SET nome = 'ES - 320530'"))
        before = self.rows()
        first = sincronizar_municipios(self.engine, self.cadastro(), backup_dir=self.root)
        self.assertEqual(first["atualizados"], 1)
        with Path(first["backup"]).open(encoding="utf-8", newline="") as stream:
            backup = list(csv.DictReader(stream))
        self.assertEqual(backup[0]["nome"], "ES - 320530")
        self.assertEqual(backup[0]["populacao"], "322869")
        self.assertEqual(self.rows(), before)
        with self.engine.connect() as conn:
            row = conn.execute(select(Municipio.__table__)).mappings().one()
            self.assertEqual(row["nome"], "Vitória")
            self.assertEqual(row["populacao"], 322869)
        again = sincronizar_municipios(self.engine, self.cadastro(), backup_dir=self.root)
        self.assertEqual(again["atualizados"], 0)
        self.assertIsNone(again["backup"])

    def test_cadastro_nao_aplica_fonte_sem_cobertura_do_banco(self):
        original = self.rows()
        other = [dict(codigo_municipio="320520", codigo_ibge_completo="3205200", nome="Vila Velha")]
        with self.assertRaisesRegex(ValueError, "sem correspondência"):
            sincronizar_municipios(self.engine, other, backup_dir=self.root)
        self.assertEqual(self.rows(), original)

    def test_falha_durante_cadastro_reverte_os_nomes(self):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE municipios SET nome = 'provisorio'"))
        def fail_update(connection, cursor, statement, parameters, context, many):
            if statement.upper().startswith("UPDATE MUNICIPIOS"):
                raise RuntimeError("falha simulada")
        event.listen(self.engine, "before_cursor_execute", fail_update)
        try:
            with self.assertRaisesRegex(RuntimeError, "falha simulada"):
                sincronizar_municipios(self.engine, self.cadastro(), backup_dir=self.root)
        finally:
            event.remove(self.engine, "before_cursor_execute", fail_update)
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(select(Municipio.nome)).scalar_one(), "provisorio")

    def test_cadastro_com_backup_inacessivel_nao_muda_nomes(self):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE municipios SET nome = 'provisorio'"))
        invalid = self.root / "arquivo"
        invalid.write_text("arquivo", encoding="utf-8")
        with self.assertRaises(OSError):
            sincronizar_municipios(self.engine, self.cadastro(), backup_dir=invalid)
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(select(Municipio.nome)).scalar_one(), "provisorio")


class NovoCadastroTests(unittest.TestCase):
    def test_cadastro_em_banco_novo_insere_nome_sem_inventar_populacao(self):
        engine = create_engine("sqlite://")
        cadastro = [dict(codigo_municipio="320530", codigo_ibge_completo="3205309", nome="Vitória")]
        try:
            result = sincronizar_municipios(engine, cadastro)
            self.assertEqual(result["inseridos"], 1)
            with engine.connect() as conn:
                row = conn.execute(select(Municipio.__table__)).mappings().one()
                self.assertEqual(row["nome"], "Vitória")
                self.assertIsNone(row["populacao"])
                self.assertEqual(list(conn.execute(select(CasoDengue.id))), [])
        finally:
            engine.dispose()


class ComandoCargaTests(unittest.TestCase):
    """Confere o comando público sem conectar ao banco configurado no ambiente."""

    def setUp(self):
        patches = ExitStack()
        self.addCleanup(patches.close)
        fontes = {
            "carregar_fonte": FonteCarga([record()], [2024]),
            "carregar_cadastro": [dict(codigo_municipio="320530")],
            "carregar_populacao": [dict(populacao=1000)],
            "carregar_clima": ([dict(codigo="A612")], [dict(ano=2026)]),
            "carregar_vinculos": [dict(ano=2026)],
            "carregar_serie_sesa": [dict(registros_notificados=7)],
        }
        self.carregadores = {
            nome: patches.enter_context(patch.object(povoar_banco, nome, return_value=fonte))
            for nome, fonte in fontes.items()
        }
        self.sincronizadores = {
            nome: patches.enter_context(patch.object(povoar_banco, nome, return_value={}))
            for nome in (
                "sincronizar_casos", "sincronizar_municipios", "sincronizar_populacoes",
                "sincronizar_clima", "sincronizar_vinculos", "sincronizar_sesa",
                "sincronizar_atualizacao_2026", "preparar_base_analitica",
            )
        }
        self.engine = patches.enter_context(patch.object(povoar_banco, "get_engine", return_value=sentinel.engine))

    def executar(self, argumentos):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            codigo = povoar_banco.main(argumentos)
        return codigo, stdout.getvalue(), stderr.getvalue()

    def test_todos_os_modos_conferem_sem_abrir_conexao_ou_aplicar(self):
        for modo in (None, "municipios", "populacao", "clima", "vinculos", "sesa",
                     "analitica", "analitica-sesa", "atualizacao-2026"):
            with self.subTest(modo=modo):
                ano = 2026 if modo == "atualizacao-2026" else 2024
                self.carregadores["carregar_fonte"].return_value = FonteCarga([record(year=ano)], [ano])
                codigo, saida, erro = self.executar([f"--{modo}"] if modo else [])
                self.assertEqual(codigo, 0, erro)
                self.assertIn("Conferência concluída", saida)
                self.assertEqual(erro, "")
        self.engine.assert_not_called()
        for sincronizar in self.sincronizadores.values():
            sincronizar.assert_not_called()

    def test_aplicar_encaminha_a_fonte_validada_e_o_backup_ao_modo_escolhido(self):
        modos = (
            (None, "carregar_fonte", "sincronizar_casos"),
            ("municipios", "carregar_cadastro", "sincronizar_municipios"),
            ("populacao", "carregar_populacao", "sincronizar_populacoes"),
            ("clima", "carregar_clima", "sincronizar_clima"),
            ("vinculos", "carregar_vinculos", "sincronizar_vinculos"),
            ("sesa", "carregar_serie_sesa", "sincronizar_sesa"),
        )
        for modo, carregador, sincronizador in modos:
            with self.subTest(modo=modo):
                argumentos = ["--aplicar", "--input", "entrada.csv", "--resumo", "resumo.json",
                              "--backup-dir", "backup-local", "--estacoes", "estacoes.csv"]
                if modo:
                    argumentos.append(f"--{modo}")
                codigo, _, erro = self.executar(argumentos)
                self.assertEqual(codigo, 0, erro)
                parametros = [Path("entrada.csv"), Path("resumo.json")]
                if modo == "clima":
                    parametros.append(Path("estacoes.csv"))
                self.carregadores[carregador].assert_called_once_with(*parametros)
                self.sincronizadores[sincronizador].assert_called_once_with(
                    sentinel.engine, self.carregadores[carregador].return_value, backup_dir=Path("backup-local"),
                )
        self.assertEqual(self.engine.call_count, len(modos))

    def test_atualizacao_2026_aplica_apenas_a_operacao_conjunta(self):
        fonte = FonteCarga([record(year=2026)], [2026])
        self.carregadores["carregar_fonte"].return_value = fonte
        codigo, _, erro = self.executar(["--atualizacao-2026", "--aplicar"])
        self.assertEqual(codigo, 0, erro)
        self.carregadores["carregar_fonte"].assert_called_once_with(
            povoar_banco.ATUALIZACAO_CSV, povoar_banco.ATUALIZACAO_RESUMO,
        )
        self.sincronizadores["sincronizar_atualizacao_2026"].assert_called_once_with(
            sentinel.engine, fonte, self.carregadores["carregar_clima"].return_value,
            self.carregadores["carregar_vinculos"].return_value, backup_dir=povoar_banco.DEFAULT_BACKUP,
        )
        self.sincronizadores["sincronizar_casos"].assert_not_called()
        self.sincronizadores["sincronizar_clima"].assert_not_called()
        self.sincronizadores["sincronizar_vinculos"].assert_not_called()

    def test_analitica_preserva_fonte_selecionada_e_recusa_entrada_csv(self):
        for modo, fonte in (("analitica", "sinan"), ("analitica-sesa", "sesa")):
            with self.subTest(fonte=fonte):
                codigo, _, erro = self.executar([f"--{modo}", "--aplicar"])
                self.assertEqual(codigo, 0, erro)
                self.sincronizadores["preparar_base_analitica"].assert_called_with(sentinel.engine, fonte=fonte)
                codigo, _, erro = self.executar([f"--{modo}", "--input", "entrada.csv", "--aplicar"])
                self.assertEqual(codigo, 1)
                self.assertIn("não recebe CSV", erro)
        self.assertEqual(self.engine.call_count, 2)

    def test_fonte_invalida_interrompe_antes_de_conectar(self):
        self.carregadores["carregar_fonte"].side_effect = ValueError("CSV e resumo não correspondem.")
        codigo, _, erro = self.executar(["--aplicar"])
        self.assertEqual(codigo, 1)
        self.assertIn("não correspondem", erro)
        self.engine.assert_not_called()

    def test_guarda_do_historico_e_exclusividade_anual_continuam_ativas(self):
        for argumentos, anos in ((["--aplicar"], [2025, 2026]),
                                 (["--atualizacao-2026", "--aplicar"], [2025])):
            with self.subTest(argumentos=argumentos):
                self.carregadores["carregar_fonte"].return_value = FonteCarga([record()], anos)
                codigo, _, erro = self.executar(argumentos)
                self.assertEqual(codigo, 1)
                self.assertTrue(erro.startswith("Erro:"))
        self.engine.assert_not_called()

    def test_erro_do_banco_nao_expoe_detalhes_da_conexao(self):
        self.sincronizadores["sincronizar_casos"].side_effect = SQLAlchemyError("segredo-ficticio-do-teste")
        codigo, saida, erro = self.executar(["--aplicar"])
        self.assertEqual(codigo, 1)
        self.assertIn("A transação foi revertida", erro)
        self.assertNotIn("segredo-ficticio-do-teste", saida + erro)


class SourceValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.csv = self.root / "source.csv"
        self.summary = self.root / "summary.json"

    def tearDown(self):
        self.directory.cleanup()

    def source(self, rows):
        with self.csv.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["codigo_municipio", "ano_epidemiologico", "semana_epidemiologica", "registos"])
            writer.writerows(rows)
        metadata = dict(
            schema_version=2, localidade="residencia", criterio="registros_notificados",
            anos_epidemiologicos=sorted({int(row[1]) for row in rows}), linhas_saida=len(rows),
            total_registos=sum(int(row[-1]) for row in rows),
            csv_sha256=hashlib.sha256(self.csv.read_bytes()).hexdigest(),
        )
        self.summary.write_text(json.dumps(metadata), encoding="utf-8")

    def test_csv_modificado_sem_resumo_e_rejeitado(self):
        self.source([["320530", 2025, 53, 7]])
        self.csv.write_text("modified", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "não correspondem"):
            carregar_fonte(self.csv, self.summary)

    def test_chave_duplicada_na_fonte_e_rejeitada(self):
        self.source([["320530", 2025, 53, 7]] * 2)
        with self.assertRaisesRegex(ValueError, "duplicada"):
            carregar_fonte(self.csv, self.summary)

    def test_semana_inexistente_naquele_ano_e_rejeitada(self):
        self.source([["320530", 2024, 53, 7]])
        with self.assertRaisesRegex(ValueError, "ano/semana"):
            carregar_fonte(self.csv, self.summary)

    def test_quantidade_negativa_e_rejeitada(self):
        self.source([["320530", 2025, 1, -7]])
        with self.assertRaisesRegex(ValueError, "valores inválidos"):
            carregar_fonte(self.csv, self.summary)

    def test_fonte_antiga_nao_pode_ser_carregada(self):
        self.csv.write_text("old", encoding="utf-8")
        self.summary.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "antiga"):
            carregar_fonte(self.csv, self.summary)


if __name__ == "__main__":
    unittest.main()
