"""Rotas HTTP: recebem filtros e devolvem os agregados consultados no banco."""

from fastapi import Depends, FastAPI, Query
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.database import DatabaseConfigurationError, get_db
from backend.models import CasoDengue, Municipio, PopulacaoMunicipal
from backend.schemas import CasoResponse, MunicipioResponse, PopulacaoResponse

app = FastAPI(title="API DenguePrev - ES", version="0.4.0")


@app.exception_handler(DatabaseConfigurationError)
def configuration_error(request, exc):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(SQLAlchemyError)
def database_error(request, exc):
    return JSONResponse(status_code=503, content={"detail": "Banco indisponível ou esquema não preparado."})


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
