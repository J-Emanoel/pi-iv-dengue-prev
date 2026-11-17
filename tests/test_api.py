import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, DatabaseConfigurationError, database_url, get_db
from backend.main import app
from backend.models import CasoDengue, Municipio


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


if __name__ == "__main__":
    unittest.main()
