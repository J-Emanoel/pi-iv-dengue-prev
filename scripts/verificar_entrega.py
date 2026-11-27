"""Confere a API por HTTP, sem enviar perguntas à LLM nem modificar o banco."""

import argparse
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlsplit

import httpx
from pydantic import TypeAdapter

from backend.schemas import (
    BaseAnaliticaResponse, BaseSesaResponse, BuscaDocumentalResponse,
    CatalogoDocumentalResponse, ComparacaoResponse, ConfiguracaoAssistenteResponse,
    ModeloPrevisaoResponse, MunicipioResponse, PrevisoesResponse,
)


@dataclass
class Verificacao:
    nome: str
    aprovado: bool
    detalhe: str


class ErroVerificacao(ValueError):
    """Mensagem escrita pelo verificador, sem conteúdo bruto do servidor."""


def _exigir(condicao, mensagem):
    if not condicao:
        raise ErroVerificacao(mensagem)


def _json(cliente, caminho, esquema=None, **kwargs):
    resposta = cliente.get(caminho, **kwargs)
    resposta.raise_for_status()
    return TypeAdapter(esquema).validate_json(resposta.content) if esquema else resposta.json()


def _cadastro(cliente):
    municipios = _json(cliente, "/municipios", list[MunicipioResponse])
    codigos = {m.codigo_ibge for m in municipios}
    _exigir(len(municipios) == len(codigos) == 78, "O cadastro deve conter 78 códigos distintos.")
    _exigir(all(m.nome.strip() and m.codigo_ibge.startswith("32") for m in municipios),
            "Há município sem nome ou fora do ES.")
    return "78 municípios com nomes e códigos distintos."


def _dados_fonte(cliente, fonte, ano):
    caminho = "/base-analitica" if fonte == "sinan" else "/base-sesa"
    esquema = BaseAnaliticaResponse if fonte == "sinan" else BaseSesaResponse
    linhas = _json(cliente, caminho, list[esquema],
                   params={"ano": ano, "codigo_municipio": "320530", "limite": 53})
    _exigir(bool(linhas), "O histórico municipal não retornou semanas.")
    _exigir(all(l.ano == ano and l.codigo_ibge == "320530" for l in linhas),
            "O histórico retornou outro recorte.")
    semanas = [l.semana_epidemiologica for l in linhas]
    _exigir(semanas == sorted(set(semanas)), "O histórico tem semanas repetidas ou fora de ordem.")
    modelo = _json(cliente, "/modelo", ModeloPrevisaoResponse, params={"fonte": fonte})
    previsao = _json(cliente, "/previsoes", PrevisoesResponse, params={"fonte": fonte})
    esperado = "sinan" if fonte == "sinan" else "sesa_esus_vs"
    _exigir(modelo.fonte_serie == previsao.modelo.fonte_serie == esperado,
            "Fonte da previsão diverge da solicitada.")
    _exigir(modelo.versao == previsao.modelo.versao, "Modelo mudou durante a verificação.")
    _exigir(previsao.total_municipios == len(previsao.resultados) == 78,
            "A previsão deve incluir os 78 municípios, inclusive indisponíveis.")
    _exigir(len({r.codigo_ibge for r in previsao.resultados}) == 78,
            "A previsão contém códigos municipais repetidos.")
    _exigir(previsao.municipios_com_previsao == sum(r.status == "disponivel" for r in previsao.resultados),
            "A quantidade de previsões disponíveis diverge dos resultados.")
    _exigir(previsao.data_inicio == previsao.data_origem + timedelta(days=1),
            "Data de origem e alvo da previsão divergem.")
    for resultado in previsao.resultados:
        disponivel = resultado.status == "disponivel"
        _exigir(disponivel == (resultado.registros_previstos is not None),
                "Status e disponibilidade numérica divergem.")
    return (f"{len(linhas)} semanas de Vitória; {modelo.familia}; "
            f"alvo {previsao.data_inicio} a {previsao.data_fim}. Não indica a semana atual.")


def _comparacao(cliente):
    dados = _json(cliente, "/comparacao", ComparacaoResponse, params={
        "codigos_municipios": ["320530", "320520"], "fonte": "sinan", "ano": 2026,
        "semana_inicial": 40, "semana_final": 43,
    })
    _exigir(dados.fonte == "sinan" and len(dados.municipios) == 2,
            "Fonte ou quantidade de municípios da comparação incorreta.")
    _exigir([m.codigo_ibge for m in dados.municipios] == ["320530", "320520"] and dados.ano == 2026,
            "O recorte municipal da comparação está incorreto.")
    comuns = set(dados.semanas_observadas_em_comum)
    observadas = [{s.semana_epidemiologica for s in m.semanas if s.registros_notificados is not None}
                 for m in dados.municipios]
    _exigir(comuns == set.intersection(*observadas) and all(40 <= s <= 43 for s in comuns),
            "Semanas comuns divergem da interseção das observações.")
    for municipio in dados.municipios:
        valores = {s.semana_epidemiologica: s.registros_notificados for s in municipio.semanas}
        _exigir(all(valores.get(s) is not None for s in comuns),
                "Semana comum sem observação municipal.")
        total = sum(valores[s] for s in comuns) if comuns else None
        _exigir(total == municipio.registros_nas_semanas_comuns,
                "Total da comparação difere das semanas comuns.")
    primeiro, segundo = dados.municipios
    diferenca = (segundo.registros_nas_semanas_comuns - primeiro.registros_nas_semanas_comuns
                 if comuns else None)
    _exigir(segundo.diferenca_para_primeiro_municipio == diferenca, "Diferença municipal incorreta.")
    return f"{len(comuns)} semanas comuns; totais e diferença conferidos com as séries."


def _documentos(cliente):
    catalogo = _json(cliente, "/documentos", CatalogoDocumentalResponse)
    busca = _json(cliente, "/documentos/busca", BuscaDocumentalResponse,
                  params={"pergunta": "Para que serve o LIRAa?"})
    _exigir(catalogo.total_trechos > 0 and busca.versao_base == catalogo.versao_base,
            "Catálogo e busca documental divergem.")
    _exigir(busca.encontrado and bool(busca.trechos), "A busca de referência não encontrou trechos.")
    return f"Base {catalogo.versao_base}; {catalogo.total_trechos} trechos; busca local operacional."


def _assistente(cliente):
    configuracao = _json(cliente, "/assistente/status", ConfiguracaoAssistenteResponse)
    _exigir(configuracao.configuracao_local_completa, "Faltam configurações do assistente no servidor.")
    return f"Configuração completa ({configuracao.modelo_llm}). Inferência real ainda não testada aqui."


def _versao(cliente):
    health = _json(cliente, "/health")
    _exigir(health.get("status") == "ok", "Health não confirmou o processo da API.")
    esquema = _json(cliente, "/openapi.json")
    versao = esquema["info"]["version"]
    _exigir(tuple(int(n) for n in versao.split(".")[:2]) >= (0, 13),
            "A API publicada ainda é anterior à cota persistente (0.13.0).")
    return f"API {versao}; processo respondendo."


def _cors(cliente, origem):
    resposta = cliente.options("/assistente", headers={
        "Origin": origem, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    })
    resposta.raise_for_status()
    _exigir(resposta.headers.get("access-control-allow-origin") != "*",
            "O CORS publicado ainda permite qualquer origem; aplique a lista explícita do backend.")
    _exigir(resposta.headers.get("access-control-allow-origin") == origem,
            "A origem da interface não foi permitida pelo CORS.")
    return "Envio do frontend permitido pelo CORS; nenhuma pergunta enviada."


def verificar(cliente, origem="https://pi-iv-dengue-prev.vercel.app"):
    verificacoes = []
    tarefas = [
        ("Versão e processo", lambda: _versao(cliente)),
        ("Cadastro IBGE", lambda: _cadastro(cliente)),
        ("Histórico e ML SINAN", lambda: _dados_fonte(cliente, "sinan", 2026)),
        ("Histórico e ML SESA", lambda: _dados_fonte(cliente, "sesa", 2024)),
        ("Comparação municipal", lambda: _comparacao(cliente)),
        ("Documentos e busca RAG", lambda: _documentos(cliente)),
        ("Configuração Groq", lambda: _assistente(cliente)),
        ("CORS da interface", lambda: _cors(cliente, origem)),
    ]
    for nome, executar in tarefas:
        try:
            verificacoes.append(Verificacao(nome, True, executar()))
        except httpx.HTTPStatusError as exc:
            verificacoes.append(Verificacao(nome, False, f"HTTP {exc.response.status_code}."))
        except httpx.HTTPError:
            verificacoes.append(Verificacao(nome, False, "Conexão indisponível ou tempo esgotado."))
        except ErroVerificacao as exc:
            verificacoes.append(Verificacao(nome, False, str(exc)))
        except (ValueError, KeyError, TypeError, AttributeError):
            # O corpo bruto e os erros de validação podem conter informações internas.
            verificacoes.append(Verificacao(nome, False, "Resposta incompatível com o contrato esperado."))
    return verificacoes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--origem", default="https://pi-iv-dengue-prev.vercel.app")
    args = parser.parse_args(argv)
    url = urlsplit(args.api)
    if (url.scheme not in ("http", "https") or not url.hostname or url.username or url.password
            or url.query or url.fragment):
        parser.error("--api deve ser um endereço HTTP/HTTPS sem credenciais ou parâmetros.")
    with httpx.Client(base_url=args.api.rstrip("/"), timeout=httpx.Timeout(90, connect=10)) as cliente:
        verificacoes = verificar(cliente, args.origem)
    for resultado in verificacoes:
        print(f"{'OK' if resultado.aprovado else 'PENDENTE'} | {resultado.nome}: {resultado.detalhe}")
    print("Verificação somente de leitura. Não mede fidelidade da LLM nem a experiência visual.")
    return 0 if all(r.aprovado for r in verificacoes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
