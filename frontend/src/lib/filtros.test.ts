import { describe, expect, it } from 'vitest';
import { intervaloSemanal, lerFiltros, parametrosFiltros, semanasNoAno } from './filtros';
import { caminhoComparacao } from '../services/api';

describe('calendário e consultas compartilháveis', () => {
  it('respeita os anos epidemiológicos de 52 e 53 semanas', () => {
    expect(semanasNoAno(2020)).toBe(53);
    expect(semanasNoAno(2025)).toBe(53);
    expect(semanasNoAno(2026)).toBe(52);
  });
  it('restaura fonte, ano, cidades e semanas a partir do link', () => {
    const filtros = lerFiltros(
      new URLSearchParams('fonte=sinan&ano=2026&municipio=320530&comparar=320520&de=40&ate=43'),
    );
    expect(lerFiltros(parametrosFiltros(filtros))).toEqual(filtros);
    expect(intervaloSemanal(filtros)).toEqual({ inicio: 40, fim: 43, maximo: 52 });
  });
  it('normaliza fonte, ano, município e semanas inválidas sem misturar as bases', () => {
    expect(
      lerFiltros(new URLSearchParams('fonte=sesa&ano=2026&municipio=355030&de=-1&ate=99')),
    ).toMatchObject({
      fonte: 'sesa',
      ano: 2024,
      codigoMunicipio: '',
      semanaInicial: 1,
      semanaFinal: 52,
    });
    const invertido = lerFiltros(new URLSearchParams('ano=2026&de=40&ate=3'));
    expect(intervaloSemanal(invertido)).toMatchObject({ inicio: 40, fim: 40 });
  });
  it('envia as duas cidades e o intervalo à comparação HTTP, sem endpoint de IA', () => {
    const caminho = caminhoComparacao(
      { fonte: 'sesa', ano: 2024, codigoMunicipio: '', semanaInicial: 2, semanaFinal: 5 },
      '320530',
      '320520',
    );
    const url = new URL(caminho, 'https://exemplo.invalid');
    expect(url.pathname).toBe('/comparacao');
    expect(url.searchParams.getAll('codigos_municipios')).toEqual(['320530', '320520']);
    expect(url.searchParams.get('semana_final')).toBe('5');
    expect(url.searchParams.get('fonte')).toBe('sesa');
  });
});
