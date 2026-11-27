import copy
import unittest

import httpx

from scripts.verificar_entrega import ErroVerificacao, _comparacao, _cors, verificar


def comparacao_ficticia():
    municipios = []
    for codigo, nome, valor in (("320530", "Vitória", 0), ("320520", "Vila Velha", 5)):
        municipios.append(dict(
            codigo_ibge=codigo, nome_municipio=nome,
            resumo_intervalo=dict(total_registros_observados=valor, semanas_consultadas=1,
                                  semanas_com_registro=1, semanas_sem_registro=0),
            registros_nas_semanas_comuns=valor, diferenca_para_primeiro_municipio=valor,
            semanas=[dict(semana_epidemiologica=40, data_inicio="2026-10-04", data_fim="2026-10-10",
                          registros_notificados=valor, registros_por_100_mil=float(valor))],
        ))
    return dict(fonte="sinan", referencia="DT_SIN_PRI", ano=2026,
                data_fim_ultima_semana_com_registros_na_fonte="2026-10-31",
                periodo=dict(inicio="2026-10-04", fim="2026-10-10"),
                semanas_observadas_em_comum=[40], municipios=municipios, limitacoes=[])


class VerificarEntregaTests(unittest.TestCase):
    def test_continua_apos_falhas_sem_post_ou_expor_corpo_do_servidor(self):
        pedidos = []

        def atender(request):
            pedidos.append(request)
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "ok"})
            if request.url.path == "/openapi.json":
                return httpx.Response(200, json={"info": {"version": "0.13.0"}})
            if request.method == "OPTIONS":
                return httpx.Response(200, headers={"access-control-allow-origin": request.headers["origin"]})
            return httpx.Response(503, json={"detail": "segredo-sintetico-nao-mostrar"})

        with httpx.Client(base_url="https://teste.invalid", transport=httpx.MockTransport(atender)) as cliente:
            resultado = verificar(cliente)
        self.assertEqual(len(resultado), 8)
        self.assertTrue(resultado[0].aprovado)
        self.assertTrue(resultado[-1].aprovado)
        self.assertTrue(all(not r.aprovado for r in resultado[1:-1]))
        self.assertEqual({p.method for p in pedidos}, {"GET", "OPTIONS"})
        self.assertNotIn("segredo-sintetico", str(resultado))

    def test_detecta_api_antiga_e_contrato_invalido_sem_expor_dados(self):
        def atender(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "ok"})
            if request.url.path == "/openapi.json":
                return httpx.Response(200, json={"info": {"version": "0.12.0"}})
            return httpx.Response(200, json={"valor": "segredo-sintetico"})

        with httpx.Client(base_url="https://teste.invalid", transport=httpx.MockTransport(atender)) as cliente:
            resultado = verificar(cliente)
        self.assertFalse(any(r.aprovado for r in resultado))
        self.assertIn("0.13.0", resultado[0].detalhe)
        self.assertNotIn("segredo-sintetico", str(resultado))

    def test_confere_comparacao_com_zero_e_rejeita_totais_ou_semanas_incorretos(self):
        dados = comparacao_ficticia()
        for alteracao in (None, "total", "semanas"):
            with self.subTest(alteracao=alteracao):
                retorno = copy.deepcopy(dados)
                if alteracao == "total":
                    retorno["municipios"][0]["registros_nas_semanas_comuns"] = 99
                if alteracao == "semanas":
                    retorno["semanas_observadas_em_comum"] = []
                with httpx.Client(base_url="https://teste.invalid", transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json=retorno),
                )) as cliente:
                    if alteracao:
                        with self.assertRaises(ErroVerificacao):
                            _comparacao(cliente)
                    else:
                        self.assertIn("totais e diferença conferidos", _comparacao(cliente))

    def test_cors_exige_a_origem_explicita_do_frontend(self):
        origem = "https://teste.invalid"
        for permitida in (origem, "*", "https://outro.invalid"):
            with self.subTest(permitida=permitida), httpx.Client(
                base_url=origem, transport=httpx.MockTransport(lambda request: httpx.Response(
                    200, headers={"access-control-allow-origin": permitida},
                )),
            ) as cliente:
                if permitida == origem:
                    self.assertIn("nenhuma pergunta enviada", _cors(cliente, origem))
                else:
                    with self.assertRaises(ErroVerificacao):
                        _cors(cliente, origem)


if __name__ == "__main__":
    unittest.main()
