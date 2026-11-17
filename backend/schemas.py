"""Formato JSON das respostas da API; a estrutura SQL fica em models.py."""

from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


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
    nome_municipio: str
    semana_epidemiologica: int = Field(ge=1, le=53)
    quantidade_casos: int = Field(ge=0, description="Contagem de registros SINAN da fonte.")


class PopulacaoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo_ibge: str
    codigo_ibge_completo: str
    nome_municipio: str
    ano: int
    populacao: int = Field(gt=0)
    data_referencia: date
    tipo: str
    fonte_url: str
    fonte_sha256: str
    observacao: str


class EstacaoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo: str
    nome: str
    uf: str
    latitude: float
    longitude: float
    altitude: float | None
    ano_metadados: int
    fonte_sha256: str


class VinculoEstacaoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo_ibge: str
    codigo_ibge_completo: str
    nome_municipio: str
    ano: int
    codigo_estacao: str
    nome_estacao: str
    latitude_municipio: float
    longitude_municipio: float
    latitude_estacao: float
    longitude_estacao: float
    altitude_estacao: float | None
    distancia_km: float
    metodo: str
    fonte_geografia_url: str
    fonte_geografia_sha256: str
    fonte_inmet_sha256: str
    observacao: str


class ClimaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo_estacao: str
    nome_estacao: str
    ano: int
    semana_epidemiologica: int
    data_inicio: date
    precipitacao_mm: float | None
    temperatura_media_c: float | None
    umidade_media_pct: float | None
    horas_observadas: int
    horas_previstas: int
    horas_precipitacao: int
    horas_temperatura: int
    horas_umidade: int
    inicio_utc: datetime
    fim_utc: datetime
    fuso: str
    fonte_sha256: str

    @field_validator("inicio_utc", "fim_utc")
    @classmethod
    def normalizar_utc(cls, valor: datetime) -> datetime:
        # SQLite não preserva tzinfo; a carga aceita somente instantes UTC.
        return valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor.astimezone(timezone.utc)

    @computed_field
    @property
    def cobertura_precipitacao_pct(self) -> float:
        return round(100 * self.horas_precipitacao / self.horas_previstas, 2)

    @computed_field
    @property
    def cobertura_temperatura_pct(self) -> float:
        return round(100 * self.horas_temperatura / self.horas_previstas, 2)

    @computed_field
    @property
    def cobertura_umidade_pct(self) -> float:
        return round(100 * self.horas_umidade / self.horas_previstas, 2)
