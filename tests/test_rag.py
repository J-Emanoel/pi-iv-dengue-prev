import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.assistente import ErroAssistente, MensagemLLM, conversar
from backend.ferramentas_ia import FerramentasIA
from backend.main import app
from backend.rag import (
    CAMINHO_BASE, BaseDocumental, BaseDocumentalIndisponivelError,
    CorpusDocumental, FonteDocumento, get_base_documental,
)
from backend.schemas import AssistenteRequest
from pipelines.preparar_rag import dividir_texto, obter_pdf, recortar_pagina
from tests.test_assistente import ProvedorSimulado, chamada


class BaseDocumentalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = BaseDocumental.carregar()
        cls.dados = json.loads(CAMINHO_BASE.read_text(encoding="utf-8"))

    def test_recupera_paginas_com_evidencia_para_perguntas_conceituais(self):
        casos = [
            ("Como eliminar criadouros do Aedes e prevenir a dengue?", {47, 48, 52, 133}),
            ("Por que a prevencao contra o mosquito deve ser feita toda semana?", {47, 49}),
            ("O controle da dengue e responsabilidade so dos moradores?", {46, 52, 133}),
            ("O que sao casos provaveis de dengue e como diferem dos notificados?", {295, 309}),
            ("Para que serve o LIRAa?", {41}),
            ("O que causa a dengue e qual e o mosquito transmissor?", {274}),
        ]
        for pergunta, paginas in casos:
            with self.subTest(pergunta=pergunta):
                resultado = self.base.buscar(pergunta)
                self.assertTrue(resultado["encontrado"])
                self.assertTrue(paginas & {t["pagina_pdf"] for t in resultado["trechos"]})

    def test_ausencia_de_evidencia_nao_vira_resposta_por_ter_a_palavra_dengue(self):
        for pergunta in ("Qual o preco do Bitcoin?", "Como configurar um roteador Wi-Fi?",
                         "Qual dose de dipirona devo tomar?",
                         "Qual esquema de vacinacao da dengue para gestantes em 2026?",
                         "Quantos casos em Vitoria hoje em 2026?"):
            with self.subTest(pergunta=pergunta):
                self.assertFalse(self.base.buscar(pergunta)["encontrado"])

    def test_acentos_limites_e_proveniencia_dos_trechos(self):
        a = self.base.buscar("O que são casos prováveis de dengue?")
        b = self.base.buscar("O que sao casos provaveis de dengue?")
        self.assertEqual([t["id"] for t in a["trechos"]], [t["id"] for t in b["trechos"]])
        fontes = self.base.fontes
        originais = {t.id: t for t in self.base.corpus.trechos}
        self.assertLessEqual(len(a["trechos"]), 3)
        for trecho in a["trechos"]:
            original = originais[trecho["id"]]
            fonte = fontes[original.fonte_id]
            self.assertEqual(trecho["trecho"], original.texto)
            self.assertEqual(trecho["url"], fonte.url_pdf + f"#page={original.pagina_pdf}")
            self.assertEqual(trecho["pagina_impressa"], original.pagina_pdf + fonte.deslocamento_pagina_impressa)
            self.assertEqual(trecho["documento_sha256"], fonte.sha256)
        for pergunta, limite in (("  ", 3), ("a"*501, 3), ("dengue", 4)):
            with self.subTest(limite=limite), self.assertRaises(ValueError):
                self.base.buscar(pergunta, limite)

    def test_base_corrompida_pagina_invalida_ou_id_duplicado_e_rejeitado(self):
        for alteracao in ("texto", "versao", "pagina", "duplicado"):
            with self.subTest(alteracao=alteracao):
                dados = copy.deepcopy(self.dados)
                if alteracao == "texto":
                    dados["trechos"][0]["texto"] += " Texto alterado."
                elif alteracao == "versao":
                    dados["versao"] = "0"*16
                elif alteracao == "pagina":
                    dados["trechos"][0]["pagina_pdf"] = 2000
                else:
                    dados["trechos"][1]["id"] = dados["trechos"][0]["id"]
                with self.assertRaises(ValidationError):
                    CorpusDocumental.model_validate(dados)

    def test_fontes_nao_admitem_urls_arbitrarias_ou_caminho_para_env(self):
        for campo, valor in (("url_pdf", "https://exemplo.invalid/manual.pdf"),
                             ("url_pdf", "file:///C:/segredo.pdf"), ("arquivo_local", "../../.env")):
            with self.subTest(campo=campo):
                fonte = copy.deepcopy(self.dados["fontes"][0])
                fonte[campo] = valor
                with self.assertRaises(ValidationError):
                    FonteDocumento.model_validate(fonte)

    def test_pdf_com_hash_diferente_e_base_ausente_falham_sem_rede(self):
        fonte = self.base.corpus.fontes[0]
        with tempfile.TemporaryDirectory() as pasta:
            p = Path(pasta) / fonte.arquivo_local
            p.write_bytes(b"%PDF-1.7 adulterado")
            with patch("pipelines.preparar_rag.httpx.stream") as rede:
                with self.assertRaises(ValueError):
                    obter_pdf(fonte, pasta, baixar=True)
                rede.assert_not_called()
            with self.assertRaises(BaseDocumentalIndisponivelError):
                BaseDocumental.carregar(Path(pasta) / "ausente.json")

    def test_extracao_preserva_termos_e_rejeita_marcadores_ausentes(self):
        texto = "Frase completa para teste documental. " * 100
        partes = list(dividir_texto(texto.strip()))
        self.assertEqual(" ".join(partes), texto.strip())
        self.assertTrue(all(len(p) <= 1000 for p in partes))
        recorte = self.base.corpus.fontes[0].recortes[0]
        with self.assertRaises(ValueError):
            recortar_pagina("Texto sem a seção selecionada.", recorte)

    def test_rotas_documentais_funcionam_sem_chave_ou_banco(self):
        with patch("backend.assistente.ClienteGroq", side_effect=AssertionError("Não chamar Groq")), patch(
            "backend.database.get_engine", side_effect=AssertionError("Não abrir banco")), TestClient(app) as http:
            fontes = http.get("/documentos")
            self.assertEqual(fontes.status_code, 200)
            self.assertEqual(fontes.json()["total_trechos"], len(self.base.corpus.trechos))
            self.assertNotIn("arquivo_local", fontes.text)
            busca = http.get("/documentos/busca", params={"pergunta": "Para que serve o LIRAa?"})
            self.assertEqual(busca.status_code, 200)
            self.assertTrue(busca.json()["encontrado"])
            self.assertEqual(http.get("/documentos/busca", params={"pergunta": "ab"}).status_code, 422)
            self.assertEqual(http.get("/documentos/busca", params={"pergunta": "dengue", "limite": 4}).status_code, 422)

    def test_base_indisponivel_nao_impede_health_e_nao_expoe_erro_interno(self):
        def indisponivel():
            raise BaseDocumentalIndisponivelError("detalhe-interno-nao-expor")
        app.dependency_overrides[get_base_documental] = indisponivel
        try:
            with TestClient(app) as http:
                response = http.get("/documentos")
                self.assertEqual(response.status_code, 503)
                self.assertNotIn("detalhe-interno", response.text)
                self.assertEqual(http.get("/health").status_code, 200)
        finally:
            app.dependency_overrides.clear()


class AssistenteRagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = BaseDocumental.carregar()

    def setUp(self):
        def banco_proibido():
            raise AssertionError("RAG não deve abrir banco")
        self.ferramentas = FerramentasIA(session_factory=banco_proibido, carregar_documentos=lambda: self.base)
        self.pergunta = "Como eliminar criadouros do Aedes e prevenir a dengue?"
        self.ref = self.base.buscar(self.pergunta)["trechos"][0]

    def ciclo(self, texto, pergunta=None):
        pergunta = pergunta or self.pergunta
        cliente = ProvedorSimulado([chamada("consultar_documentos", dict(pergunta=pergunta)),
            MensagemLLM(role="assistant", content=texto), MensagemLLM(role="assistant", content=texto)])
        return conversar(AssistenteRequest(pergunta=pergunta), cliente, self.ferramentas)

    def test_resposta_documental_inclui_apenas_referencia_recuperada(self):
        resposta = self.ciclo(f"Elimine ou vede criadouros. [{self.ref['id']}]")
        self.assertEqual(resposta.referencias[0].id, self.ref["id"])
        self.assertEqual(resposta.referencias[0].url, self.ref["url"])
        self.assertEqual(len(resposta.referencias), 1)

    def test_citacao_inventada_ausente_ou_url_externa_nao_chega_ao_usuario(self):
        for texto in ("Use estas medidas [R999].", "Use estas medidas sem referência.",
                      f"Use estas medidas [{self.ref['id']}, R999].",
                      f"Consulte https://exemplo.invalid/saude.pdf [{self.ref['id']}]."):
            with self.subTest(texto=texto), self.assertRaises(ErroAssistente):
                self.ciclo(texto)

    def test_citacoes_agrupadas_identificam_somente_ids_recuperados(self):
        ids = [t["id"] for t in self.base.buscar(self.pergunta, 2)["trechos"]]
        resposta = self.ciclo("Medidas de prevenção [" + ", ".join(ids) + "].")
        self.assertEqual([r.id for r in resposta.referencias], ids)

    def test_corrige_referencia_uma_vez_sem_repetir_a_busca(self):
        cliente = ProvedorSimulado([
            chamada("consultar_documentos", dict(pergunta=self.pergunta)),
            MensagemLLM(role="assistant", content="Elimine ou vede criadouros, sem citar a fonte."),
            MensagemLLM(role="assistant", content=f"Elimine ou vede criadouros. [{self.ref['id']}]"),
        ])
        resposta = conversar(AssistenteRequest(pergunta=self.pergunta), cliente, self.ferramentas)
        self.assertEqual(len(resposta.consultas), 1)
        self.assertEqual(len(cliente.requisicoes), 3)
        self.assertEqual(cliente.requisicoes[-1]["escolha"], "none")
        self.assertEqual(resposta.referencias[0].id, self.ref["id"])

    def test_busca_sem_evidencia_nao_autoriza_resposta_inventada(self):
        resposta = self.ciclo("Tome 999 comprimidos.", "Qual dose de dipirona devo tomar?")
        self.assertEqual(resposta.referencias, [])
        self.assertNotIn("999", resposta.resposta)
        self.assertFalse(resposta.consultas[0].sucesso)
        self.assertIn("documentos oficiais", resposta.resposta)

    def test_recusa_ainda_e_possivel_apos_consultar_documentos(self):
        resposta = self.ciclo('{"motivo":"fora_escopo"}')
        self.assertEqual(resposta.referencias, [])
        self.assertIn("Espírito Santo", resposta.resposta)

    def test_documento_nao_cria_capacidade_de_executar_sql(self):
        cliente = ProvedorSimulado([
            chamada("consultar_documentos", dict(pergunta=self.pergunta), "doc_1"),
            chamada("executar_sql", dict(sql="DELETE FROM municipios"), "sql_1"),
            MensagemLLM(role="assistant", content='{"motivo":"escrita"}'),
        ])
        resposta = conversar(AssistenteRequest(pergunta=self.pergunta), cliente, self.ferramentas)
        self.assertFalse(resposta.consultas[1].sucesso)
        self.assertEqual(resposta.consultas[1].resultado["erro"], "ferramenta_nao_permitida")
        self.assertEqual(resposta.referencias, [])


if __name__ == "__main__":
    unittest.main()
