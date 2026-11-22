"""Rotas HTTP: recebem filtros e devolvem os agregados consultados no banco."""

from datetime import date
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from pydantic import ValidationError

from backend.analitica import BASE_ANALITICA, BASE_SESA, consulta_cobertura
from backend.assistente import ErroAssistente, conversar, get_cliente_groq, status_configuracao
from backend.database import DatabaseConfigurationError, get_db
from backend.models import (
    CasoDengue, ClimaSemanal, EstacaoMeteorologica, Municipio, PopulacaoMunicipal, VinculoMunicipioEstacao,
)
from backend.previsoes import (
    ConsultaPrevisaoError, PrevisaoIndisponivelError, ServicoPrevisoes, get_servico_previsoes,
)
from backend.ferramentas_ia import ComparacaoArgs, get_ferramentas_ia
from backend.rag import BaseDocumental, BaseDocumentalIndisponivelError, get_base_documental
from backend.schemas import (
    BaseAnaliticaResponse, BaseSesaResponse, CasoResponse, ClimaResponse, CoberturaResponse, CoberturaSesaResponse,
    EstacaoResponse, ModeloPrevisaoResponse, MunicipioResponse, PopulacaoResponse,
    PrevisoesResponse, VinculoEstacaoResponse,
    AssistenteRequest, AssistenteResponse, ConfiguracaoAssistenteResponse,
    BuscaDocumentalResponse, CatalogoDocumentalResponse, ComparacaoResponse,
)

from fastapi.middleware.cors import CORSMiddleware
app = FastAPI(title="API DenguePrev - ES", version="0.12.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(BaseDocumentalIndisponivelError)
def document_error(request, exc):
    return JSONResponse(status_code=503, content={"detail": "Base documental indisponível."})


@app.exception_handler(DatabaseConfigurationError)
def configuration_error(request, exc):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(SQLAlchemyError)
def database_error(request, exc):
    return JSONResponse(status_code=503, content={"detail": "Banco indisponível ou esquema não preparado."})


@app.exception_handler(PrevisaoIndisponivelError)
def prediction_error(request, exc):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(ErroAssistente)
def assistant_error(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


@app.get("/")
def home():
    return {"mensagem": "Bem-vindo à API do DenguePrev!"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "DenguePrev API"}


@app.get("/municipios", response_model=list[MunicipioResponse])
def listar_municipios(db: Session = Depends(get_db)):
    return db.query(Municipio).order_by(Municipio.codigo_ibge).all()


@app.get("/casos", response_model=list[CasoResponse])
def listar_casos(
    ano: int | None = Query(default=None, ge=1900, le=9998),
    codigo_municipio: str | None = Query(default=None, pattern=r"^32\d{4}$"),
    semana: int | None = Query(default=None, ge=1, le=53),
    db: Session = Depends(get_db),
):
    query = db.query(
        CasoDengue.id, CasoDengue.codigo_ibge, CasoDengue.ano,
        CasoDengue.semana_epidemiologica, CasoDengue.quantidade_casos,
        Municipio.nome.label("nome_municipio"),
    ).join(Municipio, CasoDengue.codigo_ibge == Municipio.codigo_ibge)
    if ano is not None:
        query = query.filter(CasoDengue.ano == ano)
    if codigo_municipio is not None:
        query = query.filter(CasoDengue.codigo_ibge == codigo_municipio)
    if semana is not None:
        query = query.filter(CasoDengue.semana_epidemiologica == semana)
    return query.order_by(
        CasoDengue.ano, CasoDengue.semana_epidemiologica, CasoDengue.codigo_ibge
    ).all()


@app.get("/populacoes", response_model=list[PopulacaoResponse])
def listar_populacoes(
    ano: int | None = Query(default=None, ge=1900, le=9998),
    codigo_municipio: str | None = Query(default=None, pattern=r"^32\d{4}$"),
    db: Session = Depends(get_db),
):
    tabela = PopulacaoMunicipal.__table__
    query = db.query(*tabela.columns, Municipio.nome.label("nome_municipio")).join(
        Municipio, PopulacaoMunicipal.codigo_ibge == Municipio.codigo_ibge,
    )
    if ano is not None:
        query = query.filter(PopulacaoMunicipal.ano == ano)
    if codigo_municipio is not None:
        query = query.filter(PopulacaoMunicipal.codigo_ibge == codigo_municipio)
    return query.order_by(PopulacaoMunicipal.ano, PopulacaoMunicipal.codigo_ibge).all()


@app.get("/estacoes", response_model=list[EstacaoResponse])
def listar_estacoes(db: Session = Depends(get_db)):
    return db.query(EstacaoMeteorologica).order_by(EstacaoMeteorologica.codigo).all()


@app.get("/vinculos-estacoes", response_model=list[VinculoEstacaoResponse])
def listar_vinculos_estacoes(
    ano: int | None = Query(default=None, ge=1900, le=9998),
    codigo_municipio: str | None = Query(default=None, pattern=r"^32\d{4}$"),
    db: Session = Depends(get_db),
):
    """Estação mais próxima por pacote anual; consulte distância e ressalvas."""
    query = db.query(
        *VinculoMunicipioEstacao.__table__.columns,
        Municipio.nome.label("nome_municipio"), EstacaoMeteorologica.nome.label("nome_estacao"),
    ).join(Municipio, VinculoMunicipioEstacao.codigo_ibge == Municipio.codigo_ibge).join(
        EstacaoMeteorologica, VinculoMunicipioEstacao.codigo_estacao == EstacaoMeteorologica.codigo,
    )
    if ano is not None:
        query = query.filter(VinculoMunicipioEstacao.ano == ano)
    if codigo_municipio is not None:
        query = query.filter(VinculoMunicipioEstacao.codigo_ibge == codigo_municipio)
    return query.order_by(VinculoMunicipioEstacao.ano, VinculoMunicipioEstacao.codigo_ibge).all()


@app.get("/clima", response_model=list[ClimaResponse])
def listar_clima(
    ano: int | None = Query(default=None, ge=1900, le=9998),
    codigo_estacao: str | None = Query(default=None, pattern=r"^A\d{3}$"),
    semana: int | None = Query(default=None, ge=1, le=53),
    db: Session = Depends(get_db),
):
    query = db.query(*ClimaSemanal.__table__.columns, EstacaoMeteorologica.nome.label("nome_estacao")).join(
        EstacaoMeteorologica, ClimaSemanal.codigo_estacao == EstacaoMeteorologica.codigo,
    )
    if ano is not None:
        query = query.filter(ClimaSemanal.ano == ano)
    if codigo_estacao is not None:
        query = query.filter(ClimaSemanal.codigo_estacao == codigo_estacao)
    if semana is not None:
        query = query.filter(ClimaSemanal.semana_epidemiologica == semana)
    return query.order_by(ClimaSemanal.ano, ClimaSemanal.semana_epidemiologica, ClimaSemanal.codigo_estacao).all()


@app.get("/base-analitica", response_model=list[BaseAnaliticaResponse])
def listar_base_analitica(
    ano: int | None = Query(default=None, ge=2020, le=2026),
    codigo_municipio: str | None = Query(default=None, pattern=r"^32\d{4}$"),
    semana: int | None = Query(default=None, ge=1, le=53),
    limite: int = Query(default=500, ge=1, le=5000),
    deslocamento: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Calendário completo, registros da extração, população e clima. Ausência permanece nula."""
    tabela = BASE_ANALITICA
    query = tabela.select()
    if ano is not None:
        query = query.where(tabela.c.ano == ano)
    if codigo_municipio is not None:
        query = query.where(tabela.c.codigo_ibge == codigo_municipio)
    if semana is not None:
        query = query.where(tabela.c.semana_epidemiologica == semana)
    return db.execute(query.order_by(tabela.c.data_inicio, tabela.c.codigo_ibge).limit(limite).offset(deslocamento)).mappings().all()


@app.get("/cobertura", response_model=list[CoberturaResponse])
def listar_cobertura(
    ano: int | None = Query(default=None, ge=2020, le=2026),
    codigo_municipio: str | None = Query(default=None, pattern=r"^32\d{4}$"),
    cobertura_minima_clima_pct: float = Query(default=80, ge=0, le=100, allow_inf_nan=False),
    db: Session = Depends(get_db),
):
    """Presença por município/ano. O limiar climático é exploratório; não valida cobertura epidemiológica nem aptidão para ML."""
    tabela = BASE_ANALITICA.c
    query = consulta_cobertura(cobertura_minima_clima_pct)
    if ano is not None:
        query = query.where(tabela.ano == ano)
    if codigo_municipio is not None:
        query = query.where(tabela.codigo_ibge == codigo_municipio)
    return db.execute(query.order_by(tabela.ano, tabela.codigo_ibge)).mappings().all()


@app.get("/base-sesa", response_model=list[BaseSesaResponse])
def listar_base_sesa(
    ano: int | None = Query(default=None, ge=2020, le=2024),
    codigo_municipio: str | None = Query(default=None, pattern=r"^32\d{4}$"),
    semana: int | None = Query(default=None, ge=1, le=53),
    limite: int = Query(default=500, ge=1, le=5000),
    deslocamento: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """SESA por semana de notificação com população e clima; fonte adotada para o ML retrospectivo."""
    tabela = BASE_SESA
    query = tabela.select()
    if ano is not None:
        query = query.where(tabela.c.ano == ano)
    if codigo_municipio is not None:
        query = query.where(tabela.c.codigo_ibge == codigo_municipio)
    if semana is not None:
        query = query.where(tabela.c.semana_epidemiologica == semana)
    return db.execute(query.order_by(tabela.c.data_inicio, tabela.c.codigo_ibge).limit(limite).offset(deslocamento)).mappings().all()


@app.get("/cobertura-sesa", response_model=list[CoberturaSesaResponse])
def listar_cobertura_sesa(
    ano: int | None = Query(default=None, ge=2020, le=2024),
    codigo_municipio: str | None = Query(default=None, pattern=r"^32\d{4}$"),
    cobertura_minima_clima_pct: float = Query(default=80, ge=0, le=100, allow_inf_nan=False),
    db: Session = Depends(get_db),
):
    """Presença de registros estaduais e qualidade horária; não mede a proporção de casos reais capturados."""
    tabela = BASE_SESA.c
    query = consulta_cobertura(cobertura_minima_clima_pct, fonte="sesa")
    if ano is not None:
        query = query.where(tabela.ano == ano)
    if codigo_municipio is not None:
        query = query.where(tabela.codigo_ibge == codigo_municipio)
    return db.execute(query.order_by(tabela.ano, tabela.codigo_ibge)).mappings().all()


@app.get("/modelo", response_model=ModeloPrevisaoResponse, tags=["Previsões"])
def consultar_modelo(servico: ServicoPrevisoes = Depends(get_servico_previsoes)):
    """Estratégia efetiva, versão, período, métricas e limites do experimento local."""
    return servico.modelo


@app.get("/previsoes", response_model=PrevisoesResponse, tags=["Previsões"])
def listar_previsoes(
    data_inicio: date | None = Query(default=None, description="Domingo inicial da semana alvo. Sem filtro, usa a semana seguinte ao snapshot histórico."),
    codigo_municipio: str | None = Query(default=None, pattern=r"^32\d{4}$"),
    servico: ServicoPrevisoes = Depends(get_servico_previsoes),
):
    """Estudo da fonte escolhida e projeção seguinte ao snapshot; consulte a data máxima dos dados."""
    try:
        return servico.consultar(data_inicio=data_inicio, codigo_municipio=codigo_municipio)
    except ConsultaPrevisaoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/comparacao", response_model=ComparacaoResponse)
def comparar_municipios(
    codigos_municipios: list[str] = Query(min_length=2, max_length=5),
    ano: int = Query(ge=2020, le=2026),
    fonte: Literal["sinan", "sesa"] = "sinan",
    semana_inicial: int = Query(default=1, ge=1, le=53),
    semana_final: int | None = Query(default=None, ge=1, le=53),
    ferramentas=Depends(get_ferramentas_ia),
):
    """Mesma comparação do assistente, sem chamar a LLM nem consumir tokens."""
    try:
        argumentos = ComparacaoArgs.model_validate(dict(codigos_municipios=codigos_municipios,
            ano=ano, fonte=fonte, semana_inicial=semana_inicial, semana_final=semana_final))
        return ferramentas.comparar_municipios(**argumentos.model_dump(), incluir_semanas=True)
    except ValidationError:
        raise HTTPException(status_code=422, detail="Informe de dois a cinco códigos municipais válidos do ES.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.get("/assistente/status", response_model=ConfiguracaoAssistenteResponse, tags=["Assistente"])
def consultar_configuracao_assistente():
    """Confere somente a configuração local; não testa acesso ao provedor."""
    return status_configuracao()


@app.post("/assistente", response_model=AssistenteResponse, tags=["Assistente"])
def perguntar_assistente(
    pedido: AssistenteRequest,
    cliente=Depends(get_cliente_groq),
    ferramentas=Depends(get_ferramentas_ia),
):
    """LLM via Groq consulta agregados e documentos oficiais pelas funções permitidas."""
    return conversar(pedido, cliente, ferramentas)


@app.get("/documentos", response_model=CatalogoDocumentalResponse, tags=["Documentos"])
def listar_documentos(base: BaseDocumental = Depends(get_base_documental)):
    """Fontes, edições e versão da base local; não chama a LLM."""
    return base.listar_fontes()


@app.get("/documentos/busca", response_model=BuscaDocumentalResponse, tags=["Documentos"])
def buscar_documentos(
    pergunta: str = Query(min_length=3, max_length=500),
    limite: int = Query(default=3, ge=1, le=3),
    base: BaseDocumental = Depends(get_base_documental),
):
    """Trechos com página e link oficial; busca local sem consumir tokens do Groq."""
    try:
        return base.buscar(pergunta, limite)
    except ValueError:
        raise HTTPException(status_code=422, detail="Confira a pergunta e o limite de trechos.") from None
