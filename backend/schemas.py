"""Formato JSON das respostas da API; a estrutura SQL fica em models.py."""

from pydantic import BaseModel, ConfigDict, Field


class MunicipioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo_ibge: str
    nome: str
    populacao: int | None


class CasoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo_ibge: str
    ano: int
    semana_epidemiologica: int = Field(ge=1, le=53)
    quantidade_casos: int = Field(ge=0, description="Contagem de registros SINAN da fonte.")
