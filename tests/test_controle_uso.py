"""Chat público e cota com relógio controlado; sem Groq ou banco externo."""
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.assistente import get_cliente_groq
from backend.controle_uso import ControleUso, ErroControleUso, LimitesUso, get_controle_uso, preparar_controle
from backend.ferramentas_ia import get_ferramentas_ia
from backend.main import app
from backend.models import ControleUsoAssistente
from backend.schemas import AssistenteResponse

class BaseControleUso(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.engine = create_engine("sqlite:///" + (Path(self.pasta.name) / "cota.db").as_posix())
        preparar_controle(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.agora = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
        self.controle = ControleUso(self.sessions, LimitesUso(3, 20), lambda: self.agora)

    def tearDown(self):
        self.engine.dispose()
        self.pasta.cleanup()

    def estado(self):
        with self.sessions() as session:
            row = session.get(ControleUsoAssistente, "projeto")
            return row.pedidos_minuto, row.pedidos_dia, row.reserva_id

class ControleUsoTests(BaseControleUso):
    def test_preparacao_repetida_preserva_cota_e_nao_guarda_textos_ou_codigo(self):
        with self.controle.reservar():
            self.assertEqual(self.estado()[:2], (1, 1))
        preparar_controle(self.engine)
        self.assertEqual(self.estado(), (1, 1, None))
        self.assertEqual(set(ControleUsoAssistente.__table__.columns.keys()),
            {"chave", "minuto", "dia", "pedidos_minuto", "pedidos_dia", "reserva_id", "reserva_ate"})

    def test_cota_persiste_entre_instancias_e_falha_nao_devolve_tentativa(self):
        controle = ControleUso(self.sessions, LimitesUso(3, 1), lambda: self.agora)
        with self.assertRaisesRegex(RuntimeError, "provedor ficticio"):
            with controle.reservar():
                raise RuntimeError("provedor ficticio")
        novo = ControleUso(self.sessions, LimitesUso(3, 1), lambda: self.agora)
        with self.assertRaises(ErroControleUso) as exc, novo.reservar():
            self.fail("Cota diária deveria bloquear a segunda tentativa")
        self.assertEqual(exc.exception.status_code, 429)
        self.assertGreater(exc.exception.retry_after, 0)
        self.assertEqual(self.estado(), (1, 1, None))

    def test_janelas_de_minuto_e_dia_sao_renovadas_em_utc(self):
        controle = ControleUso(self.sessions, LimitesUso(1, 2), lambda: self.agora)
        with controle.reservar():
            pass
        with self.assertRaises(ErroControleUso), controle.reservar():
            self.fail("Limite de minuto ignorado")
        self.agora += timedelta(minutes=1)
        with controle.reservar():
            pass
        self.agora += timedelta(minutes=1)
        with self.assertRaises(ErroControleUso), controle.reservar():
            self.fail("Limite diário ignorado")
        self.agora += timedelta(days=1)
        with controle.reservar():
            pass
        self.assertEqual(self.estado(), (1, 1, None))

    def test_reserva_impede_duas_perguntas_simultaneas(self):
        entrou, liberar = Event(), Event()
        def primeira():
            with self.controle.reservar():
                entrou.set()
                self.assertTrue(liberar.wait(5))
        with ThreadPoolExecutor(max_workers=1) as executor:
            tarefa = executor.submit(primeira)
            self.assertTrue(entrou.wait(5))
            try:
                with self.assertRaises(ErroControleUso), self.controle.reservar():
                    self.fail("Duas perguntas foram admitidas juntas")
                self.assertEqual(self.estado()[:2], (1, 1))
            finally:
                liberar.set()
            tarefa.result(timeout=5)

    def test_reserva_expira_e_liberacao_antiga_nao_apaga_a_nova(self):
        antiga = self.controle._admitir()
        self.agora += timedelta(seconds=601)
        nova = self.controle._admitir()
        self.controle._finalizar(antiga)
        self.assertEqual(self.estado()[2], nova)
        self.controle._finalizar(nova)
        self.assertIsNone(self.estado()[2])

    def test_ausencia_da_tabela_bloqueia_o_consumo_com_erro_controlado(self):
        ControleUsoAssistente.__table__.drop(self.engine)
        with self.assertRaises(ErroControleUso) as exc, self.controle.reservar():
            self.fail("Consumo liberado sem armazenamento da cota")
        self.assertEqual(exc.exception.status_code, 503)
        self.assertNotIn(str(self.pasta.name), str(exc.exception))

    def test_limites_invalidos_falham_sem_reproduzir_valores(self):
        with patch.dict(os.environ, {"ASSISTENTE_LIMITE_DIA": "valor-confidencial-ficticio"}):
            with self.assertRaises(ErroControleUso) as exc:
                LimitesUso.do_ambiente()
            self.assertNotIn("valor-confidencial", str(exc.exception))


class AssistentePublicoTests(BaseControleUso):
    def setUp(self):
        super().setUp()
        app.dependency_overrides[get_controle_uso] = lambda: self.controle
        app.dependency_overrides[get_cliente_groq] = lambda: object()
        app.dependency_overrides[get_ferramentas_ia] = lambda: object()
        self.geracao = patch("backend.main.conversar", return_value=AssistenteResponse(
            resposta="Resposta fictícia do teste.", modelo_llm="modelo-ficticio", consultas=[]))
        self.conversar = self.geracao.start()
        self.http = TestClient(app)

    def tearDown(self):
        self.http.close()
        self.geracao.stop()
        app.dependency_overrides.clear()
        super().tearDown()

    def enviar(self, origem=None, **body):
        headers = {}
        if origem:
            headers["Origin"] = origem
        return self.http.post("/assistente", json={"pergunta": "Pergunta fictícia do teste.", **body}, headers=headers)

    def test_chat_publico_admite_pergunta_sem_senha(self):
        self.assertEqual(self.enviar().status_code, 200)
        self.assertEqual(self.conversar.call_count, 1)
        self.assertEqual(self.estado(), (1, 1, None))
        self.assertEqual(self.http.get("/health").status_code, 200)

    def test_limite_publico_impede_nova_geracao(self):
        self.controle.limites = LimitesUso(1, 1)
        self.assertEqual(self.enviar().status_code, 200)
        resposta = self.enviar()
        self.assertEqual(resposta.status_code, 429)
        self.assertTrue(int(resposta.headers["Retry-After"]) > 0)
        self.assertEqual(self.conversar.call_count, 1)

    def test_body_invalido_nao_reserva_cota(self):
        self.assertEqual(self.enviar(pergunta="").status_code, 422)
        self.assertEqual(self.estado(), (0, 0, None))
        self.conversar.assert_not_called()

    def test_preflight_e_origem_da_chamada_restritos_ao_frontend(self):
        origem = "https://pi-iv-dengue-prev.vercel.app"
        resposta = self.http.options("/assistente", headers={"Origin": origem,
            "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Content-Type"})
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.headers["Access-Control-Allow-Origin"], origem)
        self.assertEqual(self.enviar(origem="https://origem-invalida.invalid").status_code, 403)
        self.conversar.assert_not_called()

    def test_status_publico_depende_somente_da_configuracao_do_provedor(self):
        resposta = self.http.get("/assistente/status")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("configuracao_local_completa", resposta.json())
        self.assertNotIn("exige_codigo", resposta.json())
