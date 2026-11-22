import { describe, expect, it } from 'vitest';
import type { RegistroSemanal } from '../../types/api';
import {
  indicadoresPorMunicipio,
  populacaoDoRecorte,
  resumirIndicadores,
  resumirSensor,
  selecionarPeriodo,
  serieClimatica,
} from './analise';
import { municipiosNoMapa, corDoMapa } from './geografia';

function registro(campos: Partial<RegistroSemanal> = {}): RegistroSemanal {
  return {
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
  };
}

describe('indicadores do dashboard', () => {
  it('conta cada população uma vez e não soma o denominador por semana', () => {
    const dados = [
      registro(),
      registro({ semana_epidemiologica: 2 }),
      registro({ codigo_ibge: '320520', populacao: 2000 }),
    ];
    expect(populacaoDoRecorte(dados)).toBe(3000);
    expect(resumirIndicadores(dados).taxa).toBe(1000);
    expect(indicadoresPorMunicipio(dados).find((m) => m.codigo === '320530')?.taxa).toBe(2000);
  });
  it('preserva taxa ausente, zero observado e população desconhecida ou conflitante', () => {
    expect(resumirIndicadores([registro({ registros_notificados: null })]).taxa).toBeNull();
    expect(resumirIndicadores([registro({ registros_notificados: 0 })]).taxa).toBe(0);
    expect(
      populacaoDoRecorte([registro(), registro({ codigo_ibge: '320520', populacao: null })]),
    ).toBeNull();
    expect(populacaoDoRecorte([registro(), registro({ populacao: 2000 })])).toBeNull();
  });
  it('recorta o período sem eliminar semanas ausentes', () => {
    const dados = [
      registro(),
      registro({ semana_epidemiologica: 2, registros_notificados: null }),
      registro({ semana_epidemiologica: 3 }),
    ];
    expect(
      selecionarPeriodo(dados, {
        fonte: 'sinan',
        ano: 2026,
        codigoMunicipio: '',
        semanaInicial: 2,
        semanaFinal: 3,
      }),
    ).toEqual(dados.slice(1));
  });
  it('filtra cada sensor por sua cobertura e mantém zero real de chuva', () => {
    const dados = [
      registro(),
      registro({
        semana_epidemiologica: 2,
        temperatura_media_c: 40,
        cobertura_temperatura_pct: 79,
        precipitacao_mm: null,
      }),
    ];
    expect(serieClimatica(dados, 'temperatura').map((s) => s.valor)).toEqual([25, null]);
    expect(resumirSensor(dados, 'temperatura')).toEqual({ valor: 25, semanas: 1 });
    expect(resumirSensor(dados, 'chuva')).toEqual({ valor: 0, semanas: 1 });
    expect(resumirSensor(dados, 'temperatura', 50)).toEqual({ valor: 32.5, semanas: 2 });
  });
  it('não agrega clima de cidades que podem compartilhar uma estação', () => {
    expect(serieClimatica([registro(), registro({ codigo_ibge: '320520' })], 'chuva')).toEqual([]);
    expect(
      resumirSensor([registro({ cobertura_temperatura_pct: null })], 'temperatura').valor,
    ).toBeNull();
  });
  it('prepara 78 áreas IBGE válidas e distingue ausência de zero no mapa', () => {
    expect(new Set(municipiosNoMapa.map((m) => m.codigo)).size).toBe(78);
    expect(
      municipiosNoMapa.every(
        (m) =>
          /^32\d{4}$/.test(m.codigo) &&
          m.caminho.startsWith('M') &&
          !/NaN|Infinity/.test(m.caminho),
      ),
    ).toBe(true);
    expect(corDoMapa(null, 100)).not.toBe(corDoMapa(0, 100));
    expect(corDoMapa(0, 0)).not.toContain('url');
  });
});
