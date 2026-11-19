"""Funções permitidas à LLM: somente agregados do ES, com argumentos validados."""

import json
import unicodedata
from datetime import date
from typing import Annotated, Literal

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from backend.analitica import BASE_ANALITICA, BASE_SESA
from backend.database import DatabaseConfigurationError, SessionLocal
from backend.models import Municipio
from backend.previsoes import ConsultaPrevisaoError, PrevisaoIndisponivelError, get_servico_previsoes
from backend.rag import BaseDocumentalIndisponivelError, get_base_documental
from backend.schemas import ConsultaAssistenteResponse
from pipelines.calendario import semanas_no_ano


class Argumentos(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class MunicipiosArgs(Argumentos):
    nome: str | None = Field(default=None, min_length=1, max_length=100, description="Nome completo ou trecho; omita para listar o cadastro ES.")


class ModeloArgs(Argumentos):
    fonte: Literal["sinan", "sesa"] | None = Field(default=None, description="Fonte explícita. Se omitida, usa a selecionada na solicitação.")


class PeriodoArgs(ModeloArgs):
    ano: int = Field(ge=2020, le=2026, description="Ano epidemiológico; pode diferir do ano civil nas semanas de borda.")
    semana_inicial: int = Field(default=1, ge=1, le=53)
    semana_final: int | None = Field(default=None, ge=1, le=53, description="Omita para usar a última semana do calendário do ano.")


class HistoricoArgs(PeriodoArgs):
    codigo_municipio: str = Field(pattern=r"^32\d{4}$", description="Código municipal de seis dígitos, obtido no cadastro.")


class ComparacaoArgs(PeriodoArgs):
    codigos_municipios: list[Annotated[str, Field(pattern=r"^32\d{4}$")]] = Field(min_length=2, max_length=5)


class PrevisaoArgs(ModeloArgs):
    codigo_municipio: str | None = Field(default=None, pattern=r"^32\d{4}$", description="Omita para consultar os 78 municípios, incluindo os indisponíveis.")
    data_inicio: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Domingo inicial do alvo em ISO. Omita para a semana seguinte ao snapshot, que pode estar defasada.")


class DocumentosArgs(Argumentos):
    pergunta: str = Field(min_length=3, max_length=500, description="Pergunta conceitual ou preventiva sobre dengue para buscar nos documentos oficiais cadastrados.")
    limite: int = Field(default=2, ge=1, le=3, description="Dois trechos por padrão para limitar o contexto enviado ao Groq.")


CATALOGO = {
    "listar_municipios": (MunicipiosArgs, "Resolve nomes e códigos oficiais dos municípios do Espírito Santo. Use antes de consultar por nome; peça esclarecimento se houver ambiguidade."),
    "consultar_historico": (HistoricoArgs, "Consulta registros, taxas e clima de um município por semana. Totais são calculados no backend, preservando ausências. Para comparar cidades, use comparar_municipios."),
    "comparar_municipios": (ComparacaoArgs, "Use esta função para comparar cidades após resolver seus códigos. Compara de dois a cinco municípios na mesma fonte e intervalo. O backend calcula totais e diferenças nas semanas observadas em comum, sem inventar zeros."),
    "consultar_modelo": (ModeloArgs, "Consulta estratégia efetiva, métricas, versão, datas e limitações do experimento. Use para explicar a persistência ou a defasagem da base."),
    "consultar_previsao": (PrevisaoArgs, "Consulta estimativa do modelo para uma semana disponível, com elegibilidade e motivo de indisponibilidade. Não calcula a previsão na LLM e não inventa semanas atuais."),
    "consultar_documentos": (DocumentosArgs, "Busca até três trechos de documentos oficiais sobre prevenção, vetores e conceitos de vigilância. Use para perguntas conceituais/preventivas, citando os IDs retornados. Não fornece estatísticas atuais, diagnósticos ou receitas."),
}


def definicoes_ferramentas():
    return [dict(type="function", function=dict(name=nome, description=descricao,
                 parameters=esquema.model_json_schema())) for nome, (esquema, descricao) in CATALOGO.items()]


def normalizar_nome(nome):
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", nome) if not unicodedata.combining(c)).casefold().split())


def serializar_semana(linha):
    dados = jsonable_encoder(dict(linha))
    return {campo: round(valor, 6) if isinstance(valor, float) else valor for campo, valor in dados.items()}


class FerramentasIA:
    def __init__(self, session_factory=None, carregar_previsoes=None, carregar_documentos=None):
        self.session_factory = session_factory or SessionLocal
        self.carregar_previsoes = carregar_previsoes or get_servico_previsoes
        self.carregar_documentos = carregar_documentos or get_base_documental

    def executar(self, nome, argumentos_json, *, fonte_padrao="sinan"):
        """Nome não autorizado nunca vira SQL, expressão Python ou chamada arbitrária."""
        if nome not in CATALOGO:
            return ConsultaAssistenteResponse(ferramenta=nome, argumentos={}, sucesso=False,
                resultado=dict(erro="ferramenta_nao_permitida", mensagem="Use somente as funções declaradas."))
        esquema = CATALOGO[nome][0]
        try:
            dados = json.loads(argumentos_json)
            argumentos = esquema.model_validate(dados).model_dump()
            if "fonte" in argumentos and argumentos["fonte"] is None:
                argumentos["fonte"] = fonte_padrao
        except (ValueError, TypeError, ValidationError):
            return ConsultaAssistenteResponse(ferramenta=nome, argumentos={}, sucesso=False,
                resultado=dict(erro="argumentos_invalidos", mensagem="Confira tipos, campos permitidos, município ES e limites do esquema."))
        try:
            if nome == "listar_municipios":
                resultado = self.listar_municipios(**argumentos)
            elif nome == "consultar_historico":
                resultado = self.consultar_historico(**argumentos)
            elif nome == "comparar_municipios":
                resultado = self.comparar_municipios(**argumentos)
            elif nome == "consultar_modelo":
                resultado = self.carregar_previsoes(fonte=argumentos["fonte"]).modelo.model_dump(mode="json")
            elif nome == "consultar_documentos":
                resultado = self.carregar_documentos().buscar(**argumentos)
                if not resultado["encontrado"]:
                    return ConsultaAssistenteResponse(ferramenta=nome, argumentos=argumentos, sucesso=False,
                        resultado={**resultado, "erro": "sem_base_documental",
                            "mensagem": "Nenhum trecho suficiente foi encontrado. Não complete com conhecimento externo."})
            else:
                dia = date.fromisoformat(argumentos["data_inicio"]) if argumentos["data_inicio"] else None
                resultado = self.carregar_previsoes(fonte=argumentos["fonte"]).consultar(
                    data_inicio=dia, codigo_municipio=argumentos["codigo_municipio"],
                ).model_dump(mode="json")
            return ConsultaAssistenteResponse(ferramenta=nome, argumentos=argumentos, sucesso=True, resultado=resultado)
        except (ConsultaPrevisaoError, ValueError) as exc:
            return ConsultaAssistenteResponse(ferramenta=nome, argumentos=argumentos, sucesso=False,
                resultado=dict(erro="consulta_invalida", mensagem=str(exc)))
        except BaseDocumentalIndisponivelError:
            return ConsultaAssistenteResponse(ferramenta=nome, argumentos=argumentos, sucesso=False,
                resultado=dict(erro="base_documental_indisponivel", mensagem="A base documental está indisponível. Não substitua os trechos por conhecimento externo."))
        except (DatabaseConfigurationError, SQLAlchemyError, PrevisaoIndisponivelError):
            return ConsultaAssistenteResponse(ferramenta=nome, argumentos=argumentos, sucesso=False,
                resultado=dict(erro="dados_indisponiveis", mensagem="Não foi possível obter os dados. Confira conexão e artefatos locais; não estime valores ausentes."))

    def _consultar(self, operacao):
        with self.session_factory() as session:
            with session.begin():
                if session.get_bind().dialect.name == "postgresql":
                    session.execute(text("SET TRANSACTION READ ONLY"))
                return operacao(session)

    def listar_municipios(self, nome=None):
        def obter(session):
            rows = session.execute(select(Municipio.codigo_ibge, Municipio.nome).where(
                Municipio.codigo_ibge.like("32____"),
            ).order_by(Municipio.codigo_ibge)).mappings()
            termo = normalizar_nome(nome) if nome else ""
            matches = [dict(row) for row in rows if termo in normalizar_nome(row["nome"])]
            return dict(uf="ES", municipios=matches, quantidade=len(matches))
        return self._consultar(obter)

    def comparar_municipios(self, codigos_municipios, ano, semana_inicial=1, semana_final=None, fonte="sinan"):
        if len(set(codigos_municipios)) != len(codigos_municipios):
            raise ValueError("Informe municípios distintos para a comparação.")
        historicos = [self.consultar_historico(codigo, ano, semana_inicial, semana_final, fonte)
                      for codigo in codigos_municipios]
        conjuntos = [{s["semana_epidemiologica"] for s in h["semanas"] if s["registros_notificados"] is not None}
                     for h in historicos]
        comuns = set.intersection(*conjuntos)
        municipios = []
        for historico in historicos:
            total = sum(s["registros_notificados"] for s in historico["semanas"]
                        if s["semana_epidemiologica"] in comuns) if comuns else None
            municipios.append(dict(codigo_ibge=historico["codigo_ibge"], nome_municipio=historico["nome_municipio"],
                resumo_intervalo=historico["resumo"], registros_nas_semanas_comuns=total))
        referencia = municipios[0]["registros_nas_semanas_comuns"]
        for municipio in municipios:
            municipio["diferenca_para_primeiro_municipio"] = (
                municipio["registros_nas_semanas_comuns"] - referencia if comuns else None)
        return dict(fonte=fonte, referencia=historicos[0]["referencia"], ano=ano,
            data_fim_ultima_semana_com_registros_na_fonte=historicos[0]["data_fim_ultima_semana_com_registros_na_fonte"],
            periodo=historicos[0]["periodo"], semanas_observadas_em_comum=sorted(comuns), municipios=municipios,
            limitacoes=["A comparação soma somente as mesmas semanas observadas nos municípios. Ausência não foi convertida em zero.",
                        "Totais de registros não controlam diferenças populacionais nem validam cobertura epidemiológica."])

    def consultar_historico(self, codigo_municipio, ano, semana_inicial=1, semana_final=None, fonte="sinan"):
        ultima_semana = semanas_no_ano(ano) if semana_final is None else semana_final
        if fonte == "sesa" and ano > 2024:
            raise ValueError("A série SESA disponível termina em 2024. Não substitua pela fonte SINAN silenciosamente.")
        if not semana_inicial <= ultima_semana <= semanas_no_ano(ano):
            raise ValueError("Intervalo incompatível com o calendário epidemiológico do ano.")
        tabela = BASE_ANALITICA if fonte == "sinan" else BASE_SESA
        t = tabela.c
        campos = ("codigo_ibge", "nome_municipio", "semana_epidemiologica", "data_inicio", "data_fim",
                  "registros_notificados", "registros_por_100_mil", "populacao", "data_referencia_populacao",
                  "tipo_populacao", "precipitacao_mm", "temperatura_media_c",
                  "umidade_media_pct", "cobertura_precipitacao_pct", "cobertura_temperatura_pct", "cobertura_umidade_pct")

        def obter(session):
            rows = session.execute(select(*[t[c] for c in campos]).where(
                t.codigo_ibge == codigo_municipio, t.ano == ano,
                t.semana_epidemiologica.between(semana_inicial, ultima_semana),
            ).order_by(t.data_inicio)).mappings().all()
            if not rows:
                raise ValueError("Município ou período não encontrado na base da fonte selecionada.")
            ultima = session.scalar(select(func.max(t.data_fim)).where(t.registros_notificados.is_not(None)))
            quantidades = [r["registros_notificados"] for r in rows if r["registros_notificados"] is not None]
            semanas = [serializar_semana(row) for row in rows]
            return dict(
                codigo_ibge=codigo_municipio, nome_municipio=rows[0]["nome_municipio"], fonte=fonte,
                referencia="DT_SIN_PRI" if fonte == "sinan" else "DATA_NOTIFICACAO", ano=ano,
                tipo_periodo="ano_epidemiologico",
                data_fim_ultima_semana_com_registros_na_fonte=ultima.isoformat() if ultima else None,
                periodo=dict(inicio=rows[0]["data_inicio"].isoformat(), fim=rows[-1]["data_fim"].isoformat()),
                resumo=dict(total_registros_observados=sum(quantidades) if quantidades else None,
                            semanas_consultadas=len(rows), semanas_com_registro=len(quantidades),
                            semanas_sem_registro=len(rows)-len(quantidades)),
                semanas=semanas,
                limitacoes=["Ausência na extração não significa zero. Totais somam somente as semanas observadas.",
                            "Registros por 100 mil não equivalem à incidência de casos confirmados.",
                            "A última semana global não garante completude municipal nem disponibilidade em tempo real.",
                            "O clima é aproximado por estação; a cobertura dos sensores precisa ser considerada."],
            )
        return self._consultar(obter)


def get_ferramentas_ia():
    return FerramentasIA()
