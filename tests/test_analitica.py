import unittest
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, select, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.analitica import (
    ANOS, BASE_ANALITICA, BASE_SESA, NOME_VISAO, consulta_cobertura, gerar_calendario, preparar_base_analitica,
)
from backend.database import Base, get_db
from backend.main import app
from backend.models import (
    CasoDengue, ClimaSemanal, EstacaoMeteorologica, Municipio, NotificacaoEstadual, PopulacaoMunicipal,
    SemanaEpidemiologica, VinculoMunicipioEstacao,
)
from backend.povoar_banco import main as main_carga, sincronizar_sesa
from pipelines.avaliar_fontes import PAGINA_SESA, manifesto_sesa_sha256
from pipelines.calendario import inicio_ano_epidemiologico, semanas_no_ano
from tests.test_inmet import fonte_clima, fonte_vinculos


def popular_fontes(engine):
    Base.metadata.create_all(engine)
    estacao = fonte_clima()[0][0]
    populacoes = [dict(
        codigo_ibge="320530", codigo_ibge_completo="3205309", ano=ano, populacao=valor,
        data_referencia=date(ano, 7, 1), tipo="estimativa", fonte_url="https://ibge.gov.br/exemplo",
        fonte_sha256="a" * 64, observacao="Referência de teste.",
    ) for ano, valor in ((2024, 1000), (2025, 2000))]
    casos = [dict(codigo_ibge=code, ano=ano, semana_epidemiologica=week, quantidade_casos=qtd)
             for code, ano, week, qtd in (
                 ("320530", 2024, 1, 10), ("320530", 2025, 1, 10), ("320530", 2025, 2, 0),
                 ("320520", 2025, 1, 5), ("320500", 2024, 52, 3), ("320500", 2025, 3, 0),
                 ("320530", 2026, 1, 2), ("320530", 2019, 1, 99),
             )]
    vinculos = fonte_vinculos()
    for row in vinculos:
        if row["ano"] == 2024:
            row["codigo_estacao"] = "A613"
    vinculos.append({**vinculos[-1], "codigo_ibge": "320520", "codigo_ibge_completo": "3205200"})

    def clima(codigo, ano, semana, chuva, horas):
        inicio = inicio_ano_epidemiologico(ano) + timedelta(weeks=semana - 1)
        instante = datetime.combine(inicio, time(3), tzinfo=timezone.utc)
        return dict(
            codigo_estacao=codigo, ano=ano, semana_epidemiologica=semana, data_inicio=inicio,
            precipitacao_mm=chuva, temperatura_media_c=25, umidade_media_pct=60,
            horas_observadas=168, horas_previstas=168, horas_precipitacao=horas,
            horas_temperatura=168, horas_umidade=168, inicio_utc=instante,
            fim_utc=instante + timedelta(hours=167), fuso="America/Sao_Paulo", fonte_sha256="a" * 64,
        )

    with engine.begin() as conn:
        conn.execute(Municipio.__table__.insert(), [dict(codigo_ibge=code, nome=nome) for code, nome in (
            ("320530", "Vitória"), ("320520", "Vila Velha"), ("320500", "Serra"),
        )])
        conn.execute(EstacaoMeteorologica.__table__.insert(), [estacao, {**estacao, "codigo": "A613", "nome": "Outra estação"}])
        conn.execute(PopulacaoMunicipal.__table__.insert(), populacoes)
        conn.execute(CasoDengue.__table__.insert(), casos)
        conn.execute(VinculoMunicipioEstacao.__table__.insert(), vinculos)
        conn.execute(ClimaSemanal.__table__.insert(), [
            clima("A612", 2025, 1, 0, 135), clima("A612", 2025, 2, None, 0),
            clima("A613", 2025, 1, 999, 168), clima("A613", 2024, 1, 7, 168),
        ])


class AnaliticaTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        popular_fontes(self.engine)
        self.resultado = preparar_base_analitica(self.engine)
        sessions = sessionmaker(bind=self.engine)

        def db_session():
            with sessions() as session:
                yield session

        app.dependency_overrides[get_db] = db_session
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def linha(self, ano, semana, codigo="320530"):
        with self.engine.connect() as conn:
            return conn.execute(select(BASE_ANALITICA).where(
                BASE_ANALITICA.c.ano == ano, BASE_ANALITICA.c.semana_epidemiologica == semana,
                BASE_ANALITICA.c.codigo_ibge == codigo,
            )).mappings().one()

    def test_calendario_sem_lacunas_respeita_transicao_epidemiologica(self):
        semanas = gerar_calendario()
        self.assertEqual(len(semanas), 366)
        self.assertEqual(semanas[0]["data_inicio"], date(2019, 12, 29))
        for anterior, atual in zip(semanas, semanas[1:]):
            self.assertEqual(atual["data_inicio"], anterior["data_fim"] + timedelta(days=1))
        for ano in ANOS:
            self.assertEqual(sum(row["ano"] == ano for row in semanas), semanas_no_ano(ano))

    def test_juncoes_nao_multiplicam_contagens_e_repeticao_preserva_fontes(self):
        fontes = (Municipio, CasoDengue, PopulacaoMunicipal, EstacaoMeteorologica, ClimaSemanal, VinculoMunicipioEstacao)

        def snapshot():
            with self.engine.connect() as conn:
                return [conn.execute(select(model.__table__).order_by(*model.__table__.primary_key.columns)).all() for model in fontes]

        antes = snapshot()
        self.assertEqual(self.resultado["linhas"], 3 * 366)
        self.assertEqual(self.resultado["registros_notificados"], 30)
        self.assertEqual(self.resultado["linhas_sinan"], 7)
        novamente = preparar_base_analitica(self.engine)
        self.assertEqual(novamente["semanas_inseridas"], 0)
        self.assertEqual(antes, snapshot())
        with self.engine.connect() as conn:
            rows = conn.execute(select(BASE_ANALITICA)).mappings().all()
        self.assertEqual(len(rows), len({(r["codigo_ibge"], r["ano"], r["semana_epidemiologica"]) for r in rows}))

    def test_zero_explicito_e_ausencia_permanecem_diferentes(self):
        zero, ausente = self.linha(2025, 2), self.linha(2025, 3)
        self.assertEqual(zero["registros_notificados"], 0)
        self.assertTrue(zero["registro_sinan_presente"])
        self.assertEqual(zero["registros_por_100_mil"], 0)
        self.assertIsNone(ausente["registros_notificados"])
        self.assertFalse(ausente["registro_sinan_presente"])
        self.assertIsNone(ausente["registros_por_100_mil"])

    def test_indicador_usa_populacao_do_ano_e_preserva_falta_de_denominador(self):
        self.assertEqual(self.linha(2024, 1)["registros_por_100_mil"], 1000)
        atual = self.linha(2025, 1)
        self.assertEqual(atual["registros_por_100_mil"], 500)
        self.assertEqual(atual["data_referencia_populacao"], date(2025, 7, 1))
        self.assertEqual(atual["tipo_numerador"], "registros_notificados_sinan")
        self.assertFalse(atual["cobertura_epidemiologica_validada"])
        self.assertIsNone(self.linha(2025, 1, "320520")["registros_por_100_mil"])
        self.assertEqual(self.linha(2025, 1, "320520")["codigo_ibge_completo"], "3205200")

    def test_clima_respeita_estacao_ano_e_semana_sem_vazamento_de_outras_linhas(self):
        self.assertEqual(self.linha(2024, 1)["precipitacao_mm"], 7)
        self.assertEqual(self.linha(2025, 1)["precipitacao_mm"], 0)
        sem_chuva = self.linha(2025, 2)
        self.assertTrue(sem_chuva["clima_presente"])
        self.assertIsNone(sem_chuva["precipitacao_mm"])
        self.assertEqual(sem_chuva["cobertura_precipitacao_pct"], 0)
        sem_linha = self.linha(2025, 3)
        self.assertFalse(sem_linha["clima_presente"])
        self.assertIsNone(sem_linha["cobertura_precipitacao_pct"])
        parcial = self.linha(2026, 1)
        self.assertTrue(parcial["ano_fonte_sinan_parcial"])
        self.assertIsNone(parcial["codigo_estacao"])
        self.assertFalse(parcial["representatividade_climatica_validada"])

    def test_cobertura_diferencia_presenca_de_completude_e_limiar_e_ajustavel(self):
        def consultar(limiar):
            with self.engine.connect() as conn:
                return conn.execute(consulta_cobertura(limiar).where(
                    BASE_ANALITICA.c.codigo_ibge == "320530", BASE_ANALITICA.c.ano == 2025,
                )).mappings().one()
        cobertura = consultar(80)
        self.assertEqual(cobertura["semanas_com_registros_sinan"], 2)
        self.assertEqual(cobertura["semanas_sem_registros_sinan"], semanas_no_ano(2025) - 2)
        self.assertEqual(cobertura["registros_notificados"], 10)
        self.assertEqual(cobertura["semanas_com_linha_clima"], 2)
        self.assertEqual(cobertura["semanas_clima_cobertura_suficiente"], 1)
        self.assertEqual(cobertura["semanas_com_fontes_e_cobertura"], 1)
        self.assertEqual(consultar(81)["semanas_clima_cobertura_suficiente"], 0)
        self.assertEqual(consultar(0)["semanas_clima_cobertura_suficiente"], 1)

    def test_revisao_na_fonte_aparece_na_visao_sem_recarregar_copia(self):
        with self.engine.begin() as conn:
            conn.execute(update(CasoDengue).where(
                CasoDengue.ano == 2025, CasoDengue.semana_epidemiologica == 1, CasoDengue.codigo_ibge == "320530",
            ).values(quantidade_casos=11))
        self.assertEqual(self.linha(2025, 1)["registros_notificados"], 11)

    def test_calendario_divergente_interrompe_preparacao_sem_corrigir_silenciosamente(self):
        with self.engine.begin() as conn:
            conn.execute(update(SemanaEpidemiologica).where(
                SemanaEpidemiologica.ano == 2025, SemanaEpidemiologica.semana_epidemiologica == 1,
            ).values(data_fim=date(2025, 1, 3)))
        with self.assertRaisesRegex(ValueError, "Calendário existente incompatível"):
            preparar_base_analitica(self.engine)

    def test_chave_sinan_fora_do_calendario_impede_omissao_e_reverte_ddl(self):
        ano = next(ano for ano in ANOS if semanas_no_ano(ano) == 52)
        with self.engine.begin() as conn:
            conn.execute(CasoDengue.__table__.insert(), dict(
                codigo_ibge="320530", ano=ano, semana_epidemiologica=53, quantidade_casos=1,
            ))
        antes = inspect(self.engine).get_view_definition(NOME_VISAO)
        with self.assertRaisesRegex(ValueError, "perdeu ou multiplicou"):
            preparar_base_analitica(self.engine)
        self.assertEqual(inspect(self.engine).get_view_definition(NOME_VISAO), antes)

    def test_api_filtros_paginacao_e_nulos(self):
        url = "/base-analitica?ano=2025&codigo_municipio=320530&semana=3"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        row = response.json()[0]
        self.assertEqual(row["nome_municipio"], "Vitória")
        self.assertIsNone(row["registros_notificados"])
        self.assertIsNone(row["cobertura_precipitacao_pct"])
        self.assertFalse(row["cobertura_epidemiologica_validada"])
        url = "/base-analitica?ano=2025&semana=1&limite=1"
        primeiro = self.client.get(url).json()
        segundo = self.client.get(url + "&deslocamento=1").json()
        self.assertEqual(len(primeiro), 1)
        self.assertNotEqual(primeiro[0]["codigo_ibge"], segundo[0]["codigo_ibge"])
        self.assertEqual(self.client.get("/base-analitica?ano=2025&codigo_municipio=320530").status_code, 200)
        for filtro in ("limite=5001", "deslocamento=-1", "ano=2027", "semana=0", "codigo_municipio=3205309"):
            self.assertEqual(self.client.get("/base-analitica?" + filtro).status_code, 422)

    def test_api_cobertura_sem_registros_nao_vira_total_zero(self):
        response = self.client.get("/cobertura?ano=2025&codigo_municipio=320500")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["registros_notificados"], 0)
        response = self.client.get("/cobertura?ano=2020&codigo_municipio=320500")
        self.assertIsNone(response.json()[0]["registros_notificados"])
        response = self.client.get("/cobertura?ano=2025&codigo_municipio=320530&cobertura_minima_clima_pct=81")
        self.assertEqual(response.json()[0]["semanas_clima_cobertura_suficiente"], 0)
        for filtro in ("cobertura_minima_clima_pct=101", "cobertura_minima_clima_pct=-1", "cobertura_minima_clima_pct=nan"):
            self.assertEqual(self.client.get("/cobertura?" + filtro).status_code, 422)

    def test_visao_ausente_retorna_503_sem_expor_conexao(self):
        with self.engine.begin() as conn:
            conn.exec_driver_sql(f"DROP VIEW {NOME_VISAO}")
        response = self.client.get("/base-analitica")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Banco indisponível ou esquema não preparado."})

    def test_modo_de_conferencia_nao_conecta_nem_depende_de_csv(self):
        with patch("backend.povoar_banco.get_engine") as engine:
            self.assertEqual(main_carga(["--analitica"]), 0)
            engine.assert_not_called()


def fonte_estadual():
    return [dict(codigo_ibge=code, ano=ano, semana_epidemiologica=week, registros_notificados=qtd,
                 data_referencia="DATA_NOTIFICACAO", fonte_url=PAGINA_SESA,
                 fonte_manifesto_sha256=manifesto_sesa_sha256(), fonte_csv_sha256="b" * 64)
            for code, ano, week, qtd in (("320530", 2024, 1, 20), ("320530", 2024, 2, 0),
                                        ("320520", 2023, 1, 3), ("320500", 2022, 1, 1))]


class SesaDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        popular_fontes(self.engine)
        preparar_base_analitica(self.engine)
        self.directory = tempfile.TemporaryDirectory()
        self.fonte = fonte_estadual()
        sessions = sessionmaker(bind=self.engine)

        def db_session():
            with sessions() as session:
                yield session

        app.dependency_overrides[get_db] = db_session
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()
        self.directory.cleanup()

    def carregar(self):
        return sincronizar_sesa(self.engine, self.fonte, backup_dir=self.directory.name)

    def test_carga_e_visao_preservam_fontes_e_visao_sinan(self):
        fontes = (Municipio, CasoDengue, PopulacaoMunicipal, EstacaoMeteorologica, ClimaSemanal, VinculoMunicipioEstacao, SemanaEpidemiologica)

        def snapshot():
            with self.engine.connect() as conn:
                return [conn.execute(select(model.__table__).order_by(*model.__table__.primary_key.columns)).all() for model in fontes]

        antes = snapshot()
        self.assertEqual(self.carregar()["inseridos"], 4)
        result = preparar_base_analitica(self.engine, fonte="sesa")
        self.assertEqual(result["linhas"], 3 * 261)
        self.assertEqual(result["registros_notificados"], 24)
        self.assertEqual(result["linhas_sesa"], 4)
        self.assertEqual(self.carregar()["mantidos"], 4)
        self.assertEqual(preparar_base_analitica(self.engine, fonte="sesa")["semanas_inseridas"], 0)
        self.assertEqual(antes, snapshot())
        self.assertEqual(self.client.get("/base-analitica?ano=2024&semana=1&codigo_municipio=320530").json()[0]["registros_notificados"], 10)

    def test_revisao_recebe_backup_e_falha_no_update_reverte_transacao(self):
        self.carregar()
        self.fonte[0]["registros_notificados"] = 21
        revision = self.carregar()
        self.assertEqual(revision["atualizados"], 1)
        self.assertTrue(revision["backup"])
        self.fonte[0]["registros_notificados"] = 22

        def falhar(conn, cursor, statement, params, context, many):
            if statement.startswith("UPDATE notificacoes_sesa"):
                raise RuntimeError("falha simulada")

        event.listen(self.engine, "after_cursor_execute", falhar)
        try:
            with self.assertRaisesRegex(RuntimeError, "falha simulada"):
                self.carregar()
        finally:
            event.remove(self.engine, "after_cursor_execute", falhar)
        with self.engine.connect() as conn:
            atual = conn.execute(select(NotificacaoEstadual.registros_notificados).where(
                NotificacaoEstadual.codigo_ibge == "320530", NotificacaoEstadual.ano == 2024,
                NotificacaoEstadual.semana_epidemiologica == 1,
            )).scalar_one()
        self.assertEqual(atual, 21)

    def test_fonte_parcial_nao_remove_linha_existente_e_municipio_desconhecido_e_rejeitado(self):
        self.carregar()
        self.fonte = [row for row in self.fonte if row["semana_epidemiologica"] != 2]
        with self.assertRaisesRegex(ValueError, "fora da fonte"):
            self.carregar()
        self.fonte = [{**fonte_estadual()[0], "codigo_ibge": "320000"}]
        with self.assertRaisesRegex(ValueError, "ainda não cadastrado"):
            self.carregar()

    def test_api_estadual_explica_origem_preserva_nulos_e_usa_juncoes_do_ano(self):
        self.carregar()
        preparar_base_analitica(self.engine, fonte="sesa")
        row = self.client.get("/base-sesa?ano=2024&semana=1&codigo_municipio=320530").json()[0]
        self.assertEqual(row["registros_notificados"], 20)
        self.assertEqual(row["registros_por_100_mil"], 2000)
        self.assertEqual(row["precipitacao_mm"], 7)
        self.assertEqual(row["data_referencia_registros"], "DATA_NOTIFICACAO")
        self.assertEqual(row["tipo_numerador"], "registros_notificados_sesa")
        self.assertEqual(row["fonte_registros_manifesto_sha256"], manifesto_sesa_sha256())
        self.assertNotIn("registro_sinan_presente", row)
        zero = self.client.get("/base-sesa?ano=2024&semana=2&codigo_municipio=320530").json()[0]
        self.assertEqual(zero["registros_notificados"], 0)
        self.assertTrue(zero["registro_sesa_presente"])
        ausente = self.client.get("/base-sesa?ano=2024&semana=3&codigo_municipio=320530").json()[0]
        self.assertIsNone(ausente["registros_notificados"])
        self.assertFalse(ausente["registro_sesa_presente"])
        self.assertIsNone(ausente["registros_por_100_mil"])
        self.assertEqual(self.client.get("/base-sesa?ano=2025").status_code, 422)
        coverage = self.client.get("/cobertura-sesa?ano=2024&codigo_municipio=320530").json()[0]
        self.assertEqual(coverage["semanas_com_registros_sesa"], 2)
        self.assertEqual(coverage["semanas_com_fontes_e_cobertura"], 1)
        self.assertNotIn("semanas_com_registros_sinan", coverage)

    def test_modulos_de_conferencia_estadual_nao_conectam(self):
        with patch("backend.povoar_banco.get_engine") as engine, patch(
            "backend.povoar_banco.carregar_serie_sesa", return_value=self.fonte,
        ):
            self.assertEqual(main_carga(["--sesa"]), 0)
            self.assertEqual(main_carga(["--analitica-sesa"]), 0)
            engine.assert_not_called()


if __name__ == "__main__":
    unittest.main()
