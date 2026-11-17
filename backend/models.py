"""Estrutura SQL das tabelas, colunas e restrições do histórico agregado."""

from sqlalchemy import CheckConstraint, Column, Date, ForeignKey, Index, Integer, String, Text
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
