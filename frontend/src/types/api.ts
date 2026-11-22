/** Contratos consumidos da API FastAPI. A definição completa fica em backend/schemas.py. */
export type Fonte = 'sinan' | 'sesa';

export interface FiltrosDados {
  fonte: Fonte;
  ano: number;
  codigoMunicipio: string;
}

export interface Municipio {
  codigo_ibge: string;
  nome: string;
  populacao: number | null;
}

export interface RegistroSemanal {
  codigo_ibge: string;
  nome_municipio: string;
  ano: number;
  semana_epidemiologica: number;
  data_inicio: string;
  data_fim: string;
  registros_notificados: number | null;
  registros_por_100_mil: number | null;
  populacao: number | null;
  clima_presente: boolean;
  precipitacao_mm: number | null;
  temperatura_media_c: number | null;
  umidade_media_pct: number | null;
  cobertura_precipitacao_pct: number | null;
  cobertura_temperatura_pct: number | null;
  cobertura_umidade_pct: number | null;
  ano_fonte_sinan_parcial?: boolean;
  ano_fonte_sesa_parcial?: boolean;
}

export interface Metricas {
  mae: number;
  rmse: number;
  exemplos: number;
}

export interface ModeloPrevisao {
  modelo: string;
  familia: 'persistencia' | 'random_forest' | 'gradient_boosting';
  descricao_metodo: string;
  versao: string;
  dataset_id: string;
  fonte_serie: 'sinan' | 'sesa_esus_vs';
  data_referencia_registros: string;
  inicio_historico: string;
  fim_historico: string;
  ano_validacao: number;
  ano_teste: number;
  validacao: Metricas | null;
  teste: Metricas | null;
  horizonte_semanas: number;
  limitacoes: string[];
}

export interface PrevisaoMunicipal {
  codigo_ibge: string;
  nome_municipio: string;
  status: 'disponivel' | 'dados_insuficientes';
  motivos: ('historico_incompleto' | 'clima_insuficiente')[];
  registros_previstos: number | null;
  registros_ultima_semana: number | null;
  registros_observados: number | null;
}

export interface Previsoes {
  modelo: ModeloPrevisao;
  ano: number;
  semana_epidemiologica: number;
  contexto: 'backtest_2024' | 'backtest_2025' | 'simulacao_2026' | 'projecao_apos_snapshot';
  data_inicio: string;
  data_fim: string;
  data_origem: string;
  total_municipios: number;
  municipios_com_previsao: number;
  resultados: PrevisaoMunicipal[];
}

export interface ConfiguracaoAssistente {
  modelo_llm: string | null;
  configuracao_local_completa: boolean;
  pendencias: string[];
}

export interface ReferenciaDocumento {
  id: string;
  titulo: string;
  orgao: string;
  ano: number;
  edicao: string;
  pagina_pdf: number;
  pagina_impressa: number;
  url: string;
  trecho: string;
}

export interface UsoAssistente {
  chamadas_api: number;
  respostas_com_uso: number;
  tokens_entrada: number | null;
  tokens_saida: number | null;
  tokens_total: number | null;
}

export interface RespostaAssistente {
  resposta: string;
  modelo_llm: string;
  consultas: { ferramenta: string; sucesso: boolean; argumentos: Record<string, unknown> }[];
  referencias: ReferenciaDocumento[];
  uso: UsoAssistente | null;
}

export interface MensagemHistorico {
  role: 'user' | 'assistant';
  content: string;
}

export interface CatalogoDocumental {
  versao_base: string;
  total_trechos: number;
  fontes: { id: string; titulo: string; orgao: string; ano: number; url_pdf: string }[];
}
