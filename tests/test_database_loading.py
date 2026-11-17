import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, event, insert, select, text
from sqlalchemy.exc import IntegrityError

from backend.models import CasoDengue, Municipio
from backend.povoar_banco import FonteCarga, carregar_fonte, sincronizar_casos


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
