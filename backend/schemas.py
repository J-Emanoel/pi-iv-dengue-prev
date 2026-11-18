"""Formato JSON das respostas da API; a estrutura SQL fica em models.py."""

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_serializer, field_validator


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


class AgregadoSemanalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo_ibge: str
    nome_municipio: str
    ano: int
    semana_epidemiologica: int
    data_inicio: date
    data_fim: date
    registros_notificados: int | None
    tipo_numerador: str
    cobertura_epidemiologica_validada: bool
    codigo_ibge_completo: str | None
    populacao: int | None
    data_referencia_populacao: date | None
    tipo_populacao: str | None
    fonte_populacao_url: str | None
    fonte_populacao_sha256: str | None
    observacao_populacao: str | None
    registros_por_100_mil: float | None = Field(description="Registros da extração por população anual; não é incidência de casos confirmados.")
    codigo_estacao: str | None
    nome_estacao: str | None
    distancia_km: float | None
    metodo_vinculo: str | None
    observacao_vinculo: str | None
    fonte_geografia_url: str | None
    fonte_geografia_sha256: str | None
    fonte_inmet_sha256: str | None
    representatividade_climatica_validada: bool
    clima_presente: bool
    precipitacao_mm: float | None
    temperatura_media_c: float | None
    umidade_media_pct: float | None
    horas_observadas: int | None
    horas_previstas: int | None
    horas_precipitacao: int | None
    horas_temperatura: int | None
    horas_umidade: int | None
    cobertura_precipitacao_pct: float | None
    cobertura_temperatura_pct: float | None
    cobertura_umidade_pct: float | None
    fuso: str | None

    @field_serializer("registros_por_100_mil", "cobertura_precipitacao_pct", "cobertura_temperatura_pct", "cobertura_umidade_pct")
    def arredondar_indicadores(self, valor: float | None):
        return round(valor, 6) if valor is not None else None


class BaseAnaliticaResponse(AgregadoSemanalResponse):
    registro_sinan_presente: bool
    ano_fonte_sinan_parcial: bool


class BaseSesaResponse(AgregadoSemanalResponse):
    registro_sesa_presente: bool
    ano_fonte_sesa_parcial: bool
    fonte_serie: str
    data_referencia_registros: str
    fonte_registros_url: str | None
    fonte_registros_manifesto_sha256: str | None
    fonte_registros_csv_sha256: str | None


class DiagnosticoCoberturaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo_ibge: str
    nome_municipio: str
    ano: int
    cobertura_epidemiologica_validada: bool
    representatividade_climatica_validada: bool
    semanas_calendario: int
    registros_notificados: int | None
    semanas_com_populacao: int
    semanas_com_vinculo: int
    semanas_com_linha_clima: int
    semanas_clima_cobertura_suficiente: int
    semanas_com_fontes_e_cobertura: int
    cobertura_minima_clima_pct: float


class CoberturaResponse(DiagnosticoCoberturaResponse):
    ano_fonte_sinan_parcial: bool
    semanas_com_registros_sinan: int
    semanas_sem_registros_sinan: int
    presenca_semanas_sinan_pct: float

    @field_serializer("presenca_semanas_sinan_pct")
    def arredondar_presenca(self, valor: float):
        return round(valor, 6)


class CoberturaSesaResponse(DiagnosticoCoberturaResponse):
    ano_fonte_sesa_parcial: bool
    semanas_com_registros_sesa: int
    semanas_sem_registros_sesa: int
    presenca_semanas_sesa_pct: float

    @field_serializer("presenca_semanas_sesa_pct")
    def arredondar_presenca(self, valor: float):
        return round(valor, 6)


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


class MetricasPrevisaoResponse(BaseModel):
    mae: float = Field(ge=0, allow_inf_nan=False)
    rmse: float = Field(ge=0, allow_inf_nan=False)
    exemplos: int = Field(gt=0)


class ModeloPrevisaoResponse(BaseModel):
    modelo: str
    familia: Literal["persistencia", "random_forest", "gradient_boosting"]
    descricao_metodo: str
    versao: str
    dataset_id: str
    natureza: Literal["estudo_retrospectivo"]
    fonte_serie: Literal["sesa_esus_vs", "sinan"]
    data_referencia_registros: Literal["DATA_NOTIFICACAO", "DT_SIN_PRI"]
    tipo_numerador: Literal["registros_notificados_sesa", "registros_notificados_sinan"]
    horizonte_semanas: int
    janela_semanas: int
    cobertura_minima_clima_pct: float
    inicio_historico: date
    fim_historico: date
    fim_periodo_desenvolvimento: date
    inicio_alvos_disponiveis: date
    fim_alvos_disponiveis: date
    validacao_2023: MetricasPrevisaoResponse | None = None
    teste_2024: MetricasPrevisaoResponse | None = None
    ano_validacao: int = 2023
    ano_teste: int = 2024
    validacao: MetricasPrevisaoResponse | None = None
    teste: MetricasPrevisaoResponse | None = None
    limitacoes: list[str]


class PrevisaoMunicipalResponse(BaseModel):
    codigo_ibge: str
    nome_municipio: str
    status: Literal["disponivel", "dados_insuficientes"]
    motivos: list[Literal["historico_incompleto", "clima_insuficiente"]]
    registros_previstos: float | None = Field(ge=0, allow_inf_nan=False)
    registros_ultima_semana: int | None = Field(ge=0)
    registros_observados: int | None = Field(ge=0)
    historico_completo: bool
    clima_qualificado: bool


class PrevisoesResponse(BaseModel):
    modelo: ModeloPrevisaoResponse
    contexto: Literal["backtest_2024", "backtest_2025", "simulacao_2026", "projecao_apos_snapshot"]
    ano: int
    semana_epidemiologica: int
    data_inicio: date
    data_fim: date
    data_origem: date
    total_municipios: int
    municipios_com_previsao: int
    resultados: list[PrevisaoMunicipalResponse]


class MensagemConversa(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class AssistenteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    pergunta: str = Field(min_length=1, max_length=2000)
    fonte: Literal["sinan", "sesa"] = "sinan"
    historico: list[MensagemConversa] = Field(default_factory=list, max_length=8)


class ConsultaAssistenteResponse(BaseModel):
    ferramenta: str
    argumentos: dict
    sucesso: bool
    resultado: dict


class UsoAssistenteResponse(BaseModel):
    chamadas_api: int = Field(default=0, ge=0)
    respostas_com_uso: int = Field(default=0, ge=0)
    tokens_entrada: int | None = Field(default=None, ge=0)
    tokens_saida: int | None = Field(default=None, ge=0)
    tokens_total: int | None = Field(default=None, ge=0)


class AssistenteResponse(BaseModel):
    resposta: str
    provedor: Literal["groq"] = "groq"
    modelo_llm: str
    consultas: list[ConsultaAssistenteResponse]
    uso: UsoAssistenteResponse | None = None


class ConfiguracaoAssistenteResponse(BaseModel):
    provedor: Literal["groq"] = "groq"
    modelo_llm: str | None
    configuracao_local_completa: bool
    pendencias: list[str]
