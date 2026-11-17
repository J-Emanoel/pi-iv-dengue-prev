"""Estrutura SQL das tabelas, colunas e restrições do histórico agregado."""

from sqlalchemy import CheckConstraint, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.database import Base


class Municipio(Base):
    __tablename__ = "municipios"

    codigo_ibge = Column(String, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    # Campo legado; a série histórica com referência fica em populacoes_municipais.
    populacao = Column(Integer, nullable=True)
    casos = relationship("CasoDengue", back_populates="municipio")


class CasoDengue(Base):
    __tablename__ = "casos_dengue"
    __table_args__ = (
        Index(
            "uq_casos_municipio_ano_semana",
            "codigo_ibge", "ano", "semana_epidemiologica", unique=True,
        ),
        CheckConstraint("semana_epidemiologica BETWEEN 1 AND 53", name="ck_casos_semana"),
        CheckConstraint("quantidade_casos >= 0", name="ck_casos_quantidade"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    codigo_ibge = Column(String, ForeignKey("municipios.codigo_ibge"), nullable=False)
    ano = Column(Integer, nullable=False)
    semana_epidemiologica = Column(Integer, nullable=False)
    # Por enquanto é contagem de registros SINAN, não confirmação diagnóstica.
    quantidade_casos = Column(Integer, nullable=False, default=0)
    municipio = relationship("Municipio", back_populates="casos")


class PopulacaoMunicipal(Base):
    """Denominador por ano de aplicação, com referência e origem explícitas."""

    __tablename__ = "populacoes_municipais"
    __table_args__ = (
        CheckConstraint("ano BETWEEN 1900 AND 9998", name="ck_pop_ano"),
        CheckConstraint("populacao > 0", name="ck_pop_positiva"),
    )

    codigo_ibge = Column(String, ForeignKey("municipios.codigo_ibge"), primary_key=True)
    ano = Column(Integer, primary_key=True)
    codigo_ibge_completo = Column(String(7), nullable=False)
    populacao = Column(Integer, nullable=False)
    data_referencia = Column(Date, nullable=False)
    tipo = Column(String, nullable=False)
    fonte_url = Column(Text, nullable=False)
    fonte_sha256 = Column(String(64), nullable=False)
    observacao = Column(Text, nullable=False)


class EstacaoMeteorologica(Base):
    __tablename__ = "estacoes_inmet"
    __table_args__ = (CheckConstraint("uf = 'ES'", name="ck_estacao_uf"),)

    codigo = Column(String, primary_key=True)
    nome = Column(String, nullable=False)
    uf = Column(String(2), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    altitude = Column(Float, nullable=True)
    ano_metadados = Column(Integer, nullable=False)
    fonte_sha256 = Column(String(64), nullable=False)


class ClimaSemanal(Base):
    """Observações por estação; o vínculo com municípios é uma etapa própria."""

    __tablename__ = "clima_semanal"
    __table_args__ = (
        CheckConstraint("semana_epidemiologica BETWEEN 1 AND 53", name="ck_clima_semana"),
        CheckConstraint("horas_observadas BETWEEN 1 AND 168 AND horas_previstas = 168", name="ck_clima_horas"),
        CheckConstraint("horas_precipitacao BETWEEN 0 AND horas_observadas", name="ck_clima_chuva_horas"),
        CheckConstraint("horas_temperatura BETWEEN 0 AND horas_observadas", name="ck_clima_temp_horas"),
        CheckConstraint("horas_umidade BETWEEN 0 AND horas_observadas", name="ck_clima_umid_horas"),
        CheckConstraint("precipitacao_mm IS NULL OR precipitacao_mm >= 0", name="ck_clima_chuva"),
        CheckConstraint("umidade_media_pct IS NULL OR umidade_media_pct BETWEEN 0 AND 100", name="ck_clima_umidade"),
    )

    codigo_estacao = Column(String, ForeignKey("estacoes_inmet.codigo"), primary_key=True)
    ano = Column(Integer, primary_key=True)
    semana_epidemiologica = Column(Integer, primary_key=True)
    data_inicio = Column(Date, nullable=False)
    precipitacao_mm = Column(Float, nullable=True)
    temperatura_media_c = Column(Float, nullable=True)
    umidade_media_pct = Column(Float, nullable=True)
    horas_observadas = Column(Integer, nullable=False)
    horas_previstas = Column(Integer, nullable=False)
    horas_precipitacao = Column(Integer, nullable=False)
    horas_temperatura = Column(Integer, nullable=False)
    horas_umidade = Column(Integer, nullable=False)
    inicio_utc = Column(DateTime(timezone=True), nullable=False)
    fim_utc = Column(DateTime(timezone=True), nullable=False)
    fuso = Column(String, nullable=False)
    fonte_sha256 = Column(String(64), nullable=False)


class VinculoMunicipioEstacao(Base):
    """Proximidade anual, sem afirmar representatividade meteorológica municipal."""

    __tablename__ = "municipios_estacoes"
    __table_args__ = (
        CheckConstraint("ano BETWEEN 1900 AND 9998", name="ck_vinculo_ano"),
        CheckConstraint("distancia_km >= 0", name="ck_vinculo_distancia"),
    )

    codigo_ibge = Column(String, ForeignKey("municipios.codigo_ibge"), primary_key=True)
    ano = Column(Integer, primary_key=True)
    codigo_ibge_completo = Column(String(7), nullable=False)
    codigo_estacao = Column(String, ForeignKey("estacoes_inmet.codigo"), nullable=False)
    latitude_municipio = Column(Float, nullable=False)
    longitude_municipio = Column(Float, nullable=False)
    latitude_estacao = Column(Float, nullable=False)
    longitude_estacao = Column(Float, nullable=False)
    altitude_estacao = Column(Float, nullable=True)
    distancia_km = Column(Float, nullable=False)
    metodo = Column(String, nullable=False)
    fonte_geografia_url = Column(Text, nullable=False)
    fonte_geografia_sha256 = Column(String(64), nullable=False)
    fonte_inmet_sha256 = Column(String(64), nullable=False)
    observacao = Column(Text, nullable=False)
