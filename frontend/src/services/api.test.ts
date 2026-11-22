import { afterEach, describe, expect, it, vi } from 'vitest';
import { caminhoHistorico, caminhoPrevisoes, perguntarAssistente, requisitar } from './api';
import type { MensagemHistorico } from '../types/api';

afterEach(() => vi.unstubAllGlobals());

describe('contratos e envio de requisições', () => {
  it('seleciona a rota da fonte e solicita a grade anual completa com os filtros', () => {
    expect(caminhoHistorico({ fonte: 'sinan', ano: 2026, codigoMunicipio: '' })).toBe(
      '/base-analitica?ano=2026&limite=5000',
    );
    expect(caminhoHistorico({ fonte: 'sesa', ano: 2024, codigoMunicipio: '320530' })).toBe(
      '/base-sesa?ano=2024&limite=5000&codigo_municipio=320530',
    );
    expect(caminhoPrevisoes('sinan', '320530')).toBe(
      '/previsoes?fonte=sinan&codigo_municipio=320530',
    );
  });

  it('envia uma pergunta uma única vez, com fonte e no máximo oito mensagens anteriores', async () => {
    const fetchSimulado = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ resposta: 'Texto simulado.' })));
    vi.stubGlobal('fetch', fetchSimulado);
    const historico: MensagemHistorico[] = Array.from({ length: 12 }, (_, indice) => ({
      role: 'user',
      content: `Mensagem ${indice}`,
    }));
    await perguntarAssistente(
      'Pergunta de teste',
      'sinan',
      historico,
      new AbortController().signal,
    );
    expect(fetchSimulado).toHaveBeenCalledTimes(1);
    const [url, opcoes] = fetchSimulado.mock.calls[0];
    expect(url).toMatch(/\/assistente$/);
    expect(opcoes.method).toBe('POST');
    expect(JSON.parse(opcoes.body)).toEqual({
      pergunta: 'Pergunta de teste',
      fonte: 'sinan',
      historico: historico.slice(-8),
    });
    expect(opcoes.headers.Authorization).toBeUndefined();
  });

  it('não repete uma chamada recusada pelo limite de uso', async () => {
    const fetchSimulado = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ detail: 'Limite de uso atingido.' }), { status: 429 }),
      );
    vi.stubGlobal('fetch', fetchSimulado);
    await expect(
      perguntarAssistente('Teste', 'sinan', [], new AbortController().signal),
    ).rejects.toMatchObject({ status: 429, message: 'Limite de uso atingido.' });
    expect(fetchSimulado).toHaveBeenCalledTimes(1);
  });

  it('apresenta erros de validação sem reproduzir os valores enviados', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: [{ msg: 'Campo inválido.', input: 'valor-confidencial-ficticio' }],
          }),
          { status: 422 },
        ),
      ),
    );
    await expect(requisitar('/teste')).rejects.toThrow('Campo inválido.');
  });

  it('trata falhas de conexão sem repassar a mensagem bruta da rede', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('detalhe-interno-ficticio')));
    await expect(requisitar('/municipios')).rejects.toThrow(
      'O serviço de dados está indisponível.',
    );
  });

  it('recusa uma resposta HTTP de sucesso que não contém JSON válido', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('<html>Resposta inesperada</html>')),
    );
    await expect(requisitar('/municipios')).rejects.toThrow(
      'O serviço retornou uma resposta inválida.',
    );
  });
});
