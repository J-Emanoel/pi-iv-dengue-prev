// @vitest-environment jsdom
import { cloneElement } from 'react';
import type { ReactElement } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GraficoTemporal } from './GraficoTemporal';

// O gráfico real recebe dimensões fixas porque jsdom não mede o contêiner.
vi.mock('recharts', async (original) => ({
  ...(await original<typeof import('recharts')>()),
  ResponsiveContainer: ({ children }: { children: ReactElement }) =>
    cloneElement(children as ReactElement<{ width: number; height: number }>, {
      width: 600,
      height: 300,
    }),
}));
afterEach(cleanup);

const pontos = [0, 2, null, 4, 6].map((valor, indice) => ({
  semana: indice + 1,
  inicio: '2026-01-04',
  fim: '2026-01-10',
  valores: { registros: valor },
}));

describe('apresentação compartilhada dos gráficos', () => {
  it('desenha zero como observação e interrompe a linha nas semanas ausentes', () => {
    const { container } = render(
      <GraficoTemporal
        rotulo="Histórico de teste"
        pontos={pontos}
        series={[{ chave: 'registros', nome: 'Registros', cor: '#234ac4' }]}
      />,
    );
    expect(screen.getByRole('region', { name: 'Histórico de teste' })).toBeTruthy();
    const curva = container.querySelector('.recharts-line-curve')?.getAttribute('d') ?? '';
    // Dois segmentos: semanas 1–2 e 4–5. Zero não foi removido nem a lacuna interpolada.
    expect(curva.match(/M/g)).toHaveLength(2);
    expect(curva.match(/L/g)).toHaveLength(2);
    expect(curva).not.toContain('NaN');
  });

  it('mantém a interrupção também no gráfico preenchido', () => {
    const { container } = render(
      <GraficoTemporal
        rotulo="Área de teste"
        pontos={pontos}
        preenchido
        series={[{ chave: 'registros', nome: 'Registros', cor: '#234ac4' }]}
      />,
    );
    const curva = container.querySelector('.recharts-area-curve')?.getAttribute('d') ?? '';
    expect(curva.match(/M/g)).toHaveLength(2);
    expect(curva.match(/L/g)).toHaveLength(2);
  });
});
