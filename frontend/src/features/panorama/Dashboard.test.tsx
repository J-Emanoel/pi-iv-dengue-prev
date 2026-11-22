// @vitest-environment jsdom
import { cleanup, configure, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../../App';
import type { Comparacao, RegistroSemanal } from '../../types/api';

const api = vi.hoisted(() => ({ requisitar: vi.fn() }));
configure({ asyncUtilTimeout: 5000 });
vi.mock('../../services/api', async (original) => ({
  ...(await original<typeof import('../../services/api')>()),
  requisitar: api.requisitar,
}));
// jsdom não mede layout. Os dados e controles são reais; a renderização do gráfico exige navegador.
vi.mock('recharts', async (original) => ({
  ...(await original<typeof import('recharts')>()),
  ResponsiveContainer: () => <div>Área do gráfico</div>,
}));

const municipios = [
  { codigo_ibge: '320530', nome: 'Vitória', populacao: null },
  { codigo_ibge: '320520', nome: 'Vila Velha', populacao: null },
];
const registro = (campos: Partial<RegistroSemanal> = {}): RegistroSemanal => ({
  codigo_ibge: '320530',
  nome_municipio: 'Vitória',
  ano: 2026,
  semana_epidemiologica: 1,
  data_inicio: '2026-01-04',
  data_fim: '2026-01-10',
  registros_notificados: 10,
  registros_por_100_mil: 1000,
  populacao: 1000,
  clima_presente: true,
  precipitacao_mm: 0,
  temperatura_media_c: 25,
  umidade_media_pct: 70,
  cobertura_precipitacao_pct: 100,
  cobertura_temperatura_pct: 80,
  cobertura_umidade_pct: 90,
  ...campos,
});
const registros = [
  registro(),
  registro({
    semana_epidemiologica: 2,
    registros_notificados: null,
    temperatura_media_c: 40,
    cobertura_temperatura_pct: 10,
  }),
  registro({ codigo_ibge: '320520', nome_municipio: 'Vila Velha', registros_notificados: 5 }),
];
const comparacao: Comparacao = {
  fonte: 'sinan',
  referencia: 'DT_SIN_PRI',
  ano: 2026,
  data_fim_ultima_semana_com_registros_na_fonte: '2026-01-10',
  periodo: { inicio: '2026-01-04', fim: '2026-01-17' },
  semanas_observadas_em_comum: [1],
  limitacoes: ['Somente semanas comuns.'],
  municipios: municipios.map((m, i) => ({
    codigo_ibge: m.codigo_ibge,
    nome_municipio: m.nome,
    resumo_intervalo: {
      total_registros_observados: i ? 5 : 10,
      semanas_consultadas: 2,
      semanas_com_registro: 1,
      semanas_sem_registro: 1,
    },
    registros_nas_semanas_comuns: i ? 5 : 10,
    diferenca_para_primeiro_municipio: i ? -5 : 0,
    semanas: [
      {
        semana_epidemiologica: 1,
        data_inicio: '2026-01-04',
        data_fim: '2026-01-10',
        registros_notificados: i ? 5 : 10,
        registros_por_100_mil: i ? 500 : 1000,
      },
    ],
  })),
};

beforeEach(() => {
  api.requisitar.mockReset();
  api.requisitar.mockImplementation(async (caminho: string) => {
    if (caminho === '/municipios') return municipios;
    if (caminho.startsWith('/base-analitica?')) return registros;
    if (caminho.startsWith('/comparacao?')) return comparacao;
    throw new Error('Rota inesperada no teste');
  });
});
afterEach(cleanup);

describe('exploração do dashboard sem serviços externos', () => {
  it('seleciona pelo mapa e recorta o período localmente sem repetir a leitura anual', async () => {
    render(
      <MemoryRouter initialEntries={['/?fonte=sinan&ano=2026']}>
        <App />
      </MemoryRouter>,
    );
    await screen.findByRole('heading', { name: 'Ranking de registros' });
    fireEvent.click(screen.getByRole('button', { name: 'Mapa municipal' }));
    const cidade = await screen.findByRole('button', { name: /^Vitória: 10 registros/ });
    fireEvent.keyDown(cidade, { key: 'Enter' });
    expect(screen.getByLabelText<HTMLSelectElement>('Município').value).toBe('320530');
    fireEvent.change(screen.getByLabelText('Da semana'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Histórico' }));
    expect(screen.queryByRole('heading', { name: 'Ranking de registros' })).toBeNull();
    expect(screen.getByText('Registros por semana · Vitória')).toBeTruthy();
    expect(
      api.requisitar.mock.calls.filter(([url]) => url.startsWith('/base-analitica?')),
    ).toHaveLength(1);
  });

  it('abre o contexto municipal com zero de chuva preservado e permite ajustar o sensor', async () => {
    render(
      <MemoryRouter initialEntries={['/?fonte=sinan&ano=2026&municipio=320530']}>
        <App />
      </MemoryRouter>,
    );
    await screen.findByText('Registros por semana · Vitória');
    fireEvent.click(screen.getByRole('button', { name: 'População e clima' }));
    expect(screen.getByRole('heading', { name: 'Clima associado ao município' })).toBeTruthy();
    expect(screen.getByLabelText<HTMLSelectElement>('Cobertura mínima por sensor').value).toBe(
      '80',
    );
    expect(screen.getAllByText('1 de 2 semanas com dados no critério').length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText('Indicador climático'), { target: { value: 'chuva' } });
    expect(screen.getByRole('region', { name: 'Gráfico de chuva observada' })).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Cobertura mínima por sensor'), {
      target: { value: '0' },
    });
    expect(screen.getAllByText('2 de 2 semanas com dados no critério').length).toBeGreaterThan(0);
  });

  it('compara cidades pela API de dados e bloqueia uma comparação da cidade consigo mesma', async () => {
    render(
      <MemoryRouter initialEntries={['/comparacao?fonte=sinan&ano=2026&de=1&ate=2']}>
        <App />
      </MemoryRouter>,
    );
    await screen.findByRole('heading', { name: 'Histórico nas semanas comuns' });
    const consultas = () =>
      api.requisitar.mock.calls.filter(([url]) => url.startsWith('/comparacao?'));
    expect(consultas()).toHaveLength(1);
    fireEvent.change(screen.getByLabelText('Segundo município'), { target: { value: '320530' } });
    await screen.findByRole('alert');
    expect(screen.queryByRole('heading', { name: 'Histórico nas semanas comuns' })).toBeNull();
    expect(consultas()).toHaveLength(1);
    fireEvent.change(screen.getByLabelText('Segundo município'), { target: { value: '320520' } });
    await screen.findByRole('heading', { name: 'Histórico nas semanas comuns' });
    fireEvent.click(screen.getByRole('button', { name: 'Inverter cidades' }));
    await waitFor(() => expect(consultas()).toHaveLength(3));
    const params = new URL(consultas().at(-1)![0], 'https://exemplo.invalid').searchParams;
    expect(params.getAll('codigos_municipios')).toEqual(['320520', '320530']);
    expect(params.get('semana_final')).toBe('2');
    expect(api.requisitar.mock.calls.every(([url]) => !url.includes('/assistente'))).toBe(true);
  });
});
