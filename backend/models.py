"""Estrutura SQL das tabelas, colunas e restrições do histórico agregado."""

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from backend.database import Base


class Municipio(Base):
    __tablename__ = "municipios"

    codigo_ibge = Column(String, primary_key=True, index=True)
    nome = Column(String, nullable=False)
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
