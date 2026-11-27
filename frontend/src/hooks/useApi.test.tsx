// @vitest-environment jsdom
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useApi } from './useApi';

const api = vi.hoisted(() => ({ requisitar: vi.fn() }));
vi.mock('../services/api', () => api);
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  api.requisitar.mockReset();
});

describe('inicialização lenta e troca de consulta', () => {
  it('sinaliza a espera longa e remove o aviso quando os dados chegam', async () => {
    vi.useFakeTimers();
    let concluir!: (dados: unknown) => void;
    api.requisitar.mockImplementation(
      () =>
        new Promise((resolve) => {
          concluir = resolve;
        }),
    );
    const { result } = renderHook(() => useApi('/municipios'));
    expect(result.current.carregando).toBe(true);
    expect(result.current.demorado).toBe(false);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(8000);
    });
    expect(result.current.demorado).toBe(true);
    await act(async () => concluir([{ nome: 'Vitória' }]));
    expect(result.current.carregando).toBe(false);
    expect(result.current.demorado).toBe(false);
    expect(api.requisitar).toHaveBeenCalledTimes(1);
  });

  it('cancela o aviso anterior e impede que uma resposta antiga sobrescreva outro filtro', async () => {
    vi.useFakeTimers();
    const conclusoes: ((dados: unknown) => void)[] = [];
    api.requisitar.mockImplementation(() => new Promise((resolve) => conclusoes.push(resolve)));
    const { result, rerender } = renderHook(({ caminho }) => useApi(caminho), {
      initialProps: { caminho: '/antiga' },
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });
    rerender({ caminho: '/nova' });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
      conclusoes[0]('resposta antiga');
    });
    expect(result.current.demorado).toBe(false);
    expect(result.current.dados).toBeUndefined();
    await act(async () => {
      conclusoes[1]('resposta nova');
    });
    expect(result.current.dados).toBe('resposta nova');
    expect(result.current.demorado).toBe(false);
  });
});
