// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { FiltrosDados, RespostaAssistente } from '../../types/api';
import AssistentePage from './AssistentePage';
import { limiteDaPergunta, perguntaComMunicipio } from './useConversa';

const api = vi.hoisted(() => ({ requisitar: vi.fn(), perguntarAssistente: vi.fn() }));
vi.mock('../../services/api', () => api);

const municipios = [
  { codigo_ibge: '320530', nome: 'Vitória', populacao: null },
  { codigo_ibge: '320520', nome: 'Vila Velha', populacao: null },
];
const resposta: RespostaAssistente = {
  resposta: 'Resposta simulada para testar a interação.',
  modelo_llm: 'modelo-de-teste',
  consultas: [],
  referencias: [],
  uso: null,
};

function PaginaDeTeste() {
  const [filtros, atualizar] = useState<FiltrosDados>({
    fonte: 'sinan',
    ano: 2026,
    codigoMunicipio: '320530',
  });
  return (
    <AssistentePage
      filtros={filtros}
      atualizar={atualizar}
      municipios={municipios}
      cadastroIndisponivel={false}
    />
  );
}

async function escreverEEnviar(texto = 'Qual é a previsão?') {
  fireEvent.change(screen.getByLabelText('Sua pergunta'), { target: { value: texto } });
  const enviar = screen.getByRole<HTMLButtonElement>('button', { name: 'Enviar pergunta' });
  await waitFor(() => expect(enviar.disabled).toBe(false));
  fireEvent.click(enviar);
}

beforeEach(() => {
  api.requisitar.mockReset();
  api.perguntarAssistente.mockReset();
  api.requisitar.mockImplementation(async (caminho: string) => {
    if (caminho === '/assistente/status')
      return { configuracao_local_completa: true, modelo_llm: 'modelo-de-teste', pendencias: [] };
    if (caminho === '/documentos') return { versao_base: 'teste', total_trechos: 0, fontes: [] };
    throw new Error('Rota inesperada no teste');
  });
  api.perguntarAssistente.mockResolvedValue(resposta);
});
afterEach(cleanup);

describe('conversa do assistente, sem chamadas externas', () => {
  it('preenche a sugestão sem gastar uma chamada e inclui a cidade somente no envio explícito', async () => {
    render(<PaginaDeTeste />);
    fireEvent.click(screen.getByRole('button', { name: /Consultar uma previsão/ }));
    const pergunta = screen.getByLabelText<HTMLTextAreaElement>('Sua pergunta');
    expect(pergunta.value).toContain('Vitória');
    expect(document.activeElement).toBe(pergunta);
    expect(api.perguntarAssistente).not.toHaveBeenCalled();

    const enviar = screen.getByRole<HTMLButtonElement>('button', { name: 'Enviar pergunta' });
    await waitFor(() => expect(enviar.disabled).toBe(false));
    fireEvent.click(enviar);

    await screen.findByText(resposta.resposta);
    expect(api.perguntarAssistente).toHaveBeenCalledTimes(1);
    expect(api.perguntarAssistente.mock.calls[0][0]).toMatch(/^Município de referência: Vitória\./);
    expect(api.perguntarAssistente.mock.calls[0][1]).toBe('sinan');
    expect(api.perguntarAssistente.mock.calls[0][2]).toEqual([]);
  });

  it('impede envios duplicados enquanto aguarda a resposta', async () => {
    let concluir!: (valor: RespostaAssistente) => void;
    api.perguntarAssistente.mockReturnValue(
      new Promise<RespostaAssistente>((resolve) => {
        concluir = resolve;
      }),
    );
    render(<PaginaDeTeste />);
    await escreverEEnviar();
    const botao = screen.getByRole<HTMLButtonElement>('button', { name: /Buscando resposta/ });
    fireEvent.submit(botao.closest('form')!);

    expect(botao.disabled).toBe(true);
    expect(screen.getByLabelText<HTMLTextAreaElement>('Sua pergunta').disabled).toBe(true);
    expect(api.perguntarAssistente).toHaveBeenCalledTimes(1);
    await act(async () => concluir(resposta));
    await screen.findByText(resposta.resposta);
  });

  it('inicia uma nova conversa ao trocar o município sem reutilizar o histórico anterior', async () => {
    render(<PaginaDeTeste />);
    await escreverEEnviar();
    await screen.findByText(resposta.resposta);
    fireEvent.change(screen.getByLabelText('Município de referência (opcional)'), {
      target: { value: '320520' },
    });
    expect(screen.queryByText(resposta.resposta)).toBeNull();
    await escreverEEnviar();
    await screen.findByText(resposta.resposta);
    expect(api.perguntarAssistente.mock.calls[1][0]).toContain(
      'Município de referência: Vila Velha.',
    );
    expect(api.perguntarAssistente.mock.calls[1][2]).toEqual([]);
  });

  it('mantém a pergunta para nova tentativa manual quando o serviço falha', async () => {
    api.perguntarAssistente.mockRejectedValueOnce(
      new Error('Limite de uso atingido. Tente mais tarde.'),
    );
    render(<PaginaDeTeste />);
    await escreverEEnviar('Preciso consultar os dados.');
    await screen.findByRole('alert');
    expect(screen.getByLabelText<HTMLTextAreaElement>('Sua pergunta').value).toBe(
      'Preciso consultar os dados.',
    );
    expect(api.perguntarAssistente).toHaveBeenCalledTimes(1);
    expect(
      screen.getByRole<HTMLButtonElement>('button', { name: 'Enviar pergunta' }).disabled,
    ).toBe(false);
  });

  it('reserva espaço para o município dentro do limite de texto da API', () => {
    const nome = 'Vila Velha';
    const texto = 'a'.repeat(limiteDaPergunta(nome));
    const enviado = perguntaComMunicipio(texto, nome);
    expect(enviado.length).toBe(2000);
    expect(enviado.endsWith(texto)).toBe(true);
    expect(perguntaComMunicipio(' Pergunta geral ', '')).toBe('Pergunta geral');
    expect(limiteDaPergunta('')).toBe(2000);
  });
});
