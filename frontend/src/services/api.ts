import type { FiltrosDados, Fonte, MensagemHistorico, RespostaAssistente } from '../types/api';

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

export class ErroApi extends Error {
  constructor(
    mensagem: string,
    readonly status?: number,
  ) {
    super(mensagem);
    this.name = 'ErroApi';
  }
}

function mensagemDaApi(dados: unknown): string | undefined {
  if (!dados || typeof dados !== 'object' || !('detail' in dados)) return;
  const detalhe = dados.detail;
  if (typeof detalhe === 'string') return detalhe.slice(0, 500);
  // Erros de validação podem conter valores enviados; mostramos só a mensagem.
  if (Array.isArray(detalhe)) {
    return detalhe
      .map((item: { msg?: string }) => item.msg)
      .filter(Boolean)
      .join(' ')
      .slice(0, 500);
  }
}

export async function requisitar<T>(caminho: string, opcoes: RequestInit = {}): Promise<T> {
  const limite = AbortSignal.timeout(opcoes.method === 'POST' ? 120_000 : 30_000);
  const signal = opcoes.signal ? AbortSignal.any([opcoes.signal, limite]) : limite;
  try {
    const resposta = await fetch(`${BASE_URL}${caminho}`, {
      ...opcoes,
      headers: { Accept: 'application/json', ...opcoes.headers },
      signal,
    });
    const dados: unknown = await resposta.json().catch(() => undefined);
    if (!resposta.ok) {
      throw new ErroApi(
        mensagemDaApi(dados) || 'Não foi possível concluir a consulta. Tente novamente.',
        resposta.status,
      );
    }
    if (dados === undefined) throw new ErroApi('O serviço retornou uma resposta inválida.');
    return dados as T;
  } catch (erro) {
    if (opcoes.signal?.aborted) throw erro;
    if (erro instanceof ErroApi) throw erro;
    if (limite.aborted)
      throw new ErroApi('A consulta demorou mais que o esperado. Tente novamente mais tarde.');
    throw new ErroApi(
      'O serviço de dados está indisponível. Confira se a API está em execução e tente novamente.',
    );
  }
}

export function caminhoHistorico({ fonte, ano, codigoMunicipio }: FiltrosDados): string {
  const parametros = new URLSearchParams({ ano: String(ano), limite: '5000' });
  if (codigoMunicipio) parametros.set('codigo_municipio', codigoMunicipio);
  // Um ano dos 78 municípios tem no máximo 4.134 linhas; o limite cobre a grade.
  return `/${fonte === 'sinan' ? 'base-analitica' : 'base-sesa'}?${parametros}`;
}

export function caminhoPrevisoes(fonte: Fonte, codigoMunicipio: string): string {
  const parametros = new URLSearchParams({ fonte });
  if (codigoMunicipio) parametros.set('codigo_municipio', codigoMunicipio);
  return `/previsoes?${parametros}`;
}

export function perguntarAssistente(
  pergunta: string,
  fonte: Fonte,
  historico: MensagemHistorico[],
  signal: AbortSignal,
): Promise<RespostaAssistente> {
  // Sem retry automático: uma pergunta só é enviada por uma ação explícita.
  return requisitar('/assistente', {
    method: 'POST',
    signal,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pergunta, fonte, historico: historico.slice(-8) }),
  });
}
