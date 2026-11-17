import unittest
from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, DatabaseConfigurationError, database_url, get_db
from backend.main import app
from backend.models import CasoDengue, Municipio, PopulacaoMunicipal
from backend.povoar_banco import sincronizar_clima, sincronizar_vinculos
from tests.test_inmet import fonte_clima, fonte_vinculos


class DatabaseConfigTests(unittest.TestCase):
    def test_configuracao_ausente_tem_mensagem_clara(self):
        with patch.dict("os.environ", {"DATABASE_URL": ""}):
            with self.assertRaisesRegex(DatabaseConfigurationError, "Configure DATABASE_URL"):
                database_url()

    def test_prefixos_postgres_sao_normalizados_sem_conectar(self):
        for prefix in ("postgres://", "postgresql://"):
            with self.subTest(prefix=prefix), patch.dict(
                "os.environ", {"DATABASE_URL": prefix + "localhost/dengue"},
            ):
                self.assertEqual(database_url(), "postgresql+psycopg2://localhost/dengue")


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions.begin() as session:
            session.add_all([
                Municipio(codigo_ibge="320530", nome="Vitória"),
                Municipio(codigo_ibge="320520", nome="Vila Velha"),
            ])
            session.flush()
            session.add_all([
                CasoDengue(codigo_ibge="320530", ano=2025, semana_epidemiologica=53, quantidade_casos=7),
                CasoDengue(codigo_ibge="320520", ano=2024, semana_epidemiologica=1, quantidade_casos=3),
            ])

        def session_dependency():
            with self.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = session_dependency
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_health_schema(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "DenguePrev API"})

    def test_municipios_ordenados_e_serializados(self):
        response = self.client.get("/municipios")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([m["nome"] for m in response.json()], ["Vila Velha", "Vitória"])
        self.assertIsNone(response.json()[0]["populacao"])

    def test_casos_preservam_contrato_do_dashboard(self):
        response = self.client.get("/casos")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)
        self.assertEqual(set(response.json()[0]), {
            "id", "codigo_ibge", "ano", "semana_epidemiologica", "quantidade_casos", "nome_municipio",
        })
        self.assertEqual(response.json()[0]["nome_municipio"], "Vila Velha")
        self.assertEqual(response.json()[1]["nome_municipio"], "Vitória")

    def test_filtro_combina_municipio_ano_e_semana(self):
        response = self.client.get("/casos?ano=2025&codigo_municipio=320530&semana=53")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["quantidade_casos"], 7)
        self.assertEqual(response.json()[0]["nome_municipio"], "Vitória")
        self.assertEqual(self.client.get("/casos?ano=2023").json(), [])

    def test_filtros_invalidos_retornam_422(self):
        for suffix in ("semana=54", "codigo_municipio=310620", "ano=invalid"):
            with self.subTest(suffix=suffix):
                self.assertEqual(self.client.get("/casos?" + suffix).status_code, 422)

    def test_falta_de_configuracao_do_banco_retorna_503(self):
        def unavailable():
            raise DatabaseConfigurationError("Configure DATABASE_URL.")

        app.dependency_overrides[get_db] = unavailable
        self.assertEqual(self.client.get("/casos").status_code, 503)
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_populacoes_expoe_referencia_e_preserva_filtros(self):
        with self.sessions.begin() as session:
            session.add(PopulacaoMunicipal(
                codigo_ibge="320530", codigo_ibge_completo="3205309", ano=2023,
                populacao=322869, data_referencia=date(2022, 8, 1), tipo="relacao_censitaria",
                fonte_url="https://ftp.ibge.gov.br/exemplo.ods", fonte_sha256="a" * 64,
                observacao="Relação 2023 baseada no Censo 2022.",
            ))
        response = self.client.get("/populacoes?ano=2023&codigo_municipio=320530")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        row = response.json()[0]
        self.assertEqual(row["nome_municipio"], "Vitória")
        self.assertEqual(row["data_referencia"], "2022-08-01")
        self.assertEqual(row["tipo"], "relacao_censitaria")
        self.assertEqual(self.client.get("/populacoes?ano=2024").json(), [])
        self.assertEqual(self.client.get("/populacoes?codigo_municipio=310620").status_code, 422)

    def test_clima_expoe_medicoes_e_cobertura_por_estacao(self):
        sincronizar_clima(self.engine, fonte_clima())
        stations = self.client.get("/estacoes")
        self.assertEqual(stations.status_code, 200)
        self.assertEqual(stations.json()[0]["codigo"], "A612")
        response = self.client.get("/clima?ano=2025&codigo_estacao=A612&semana=2")
        self.assertEqual(response.status_code, 200)
        row = response.json()[0]
        self.assertEqual(row["nome_estacao"], "VITÓRIA")
        self.assertEqual(row["precipitacao_mm"], 2)
        self.assertEqual(row["temperatura_media_c"], 25)
        self.assertEqual(row["cobertura_precipitacao_pct"], 1.19)
        self.assertEqual(row["fuso"], "America/Sao_Paulo")
        self.assertTrue(row["inicio_utc"].endswith("Z"))
        self.assertEqual(self.client.get("/clima?ano=2026").json(), [])
        self.assertEqual(self.client.get("/clima?codigo_estacao=320530").status_code, 422)

    def test_vinculos_expoe_distancia_metodo_e_limitacoes_com_nomes(self):
        sincronizar_clima(self.engine, fonte_clima())
        sincronizar_vinculos(self.engine, fonte_vinculos())
        response = self.client.get("/vinculos-estacoes?ano=2025&codigo_municipio=320530")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        row = response.json()[0]
        self.assertEqual(row["nome_municipio"], "Vitória")
        self.assertEqual(row["nome_estacao"], "VITÓRIA")
        self.assertEqual(row["distancia_km"], 0)
        self.assertIn("mais_proxima_por_ano", row["metodo"])
        self.assertIn("não comprova representatividade", row["observacao"])
        self.assertEqual(self.client.get("/vinculos-estacoes?ano=2026").json(), [])
        self.assertEqual(self.client.get("/vinculos-estacoes?codigo_municipio=3205309").status_code, 422)


if __name__ == "__main__":
    unittest.main()
