import type { FiltrosDados, RegistroSemanal } from '../../types/api';
import { intervaloSemanal } from '../../lib/filtros';
import { ranquearMunicipios, resumirRegistros } from './resumo';

export function selecionarPeriodo(registros: RegistroSemanal[], filtros: FiltrosDados) {
  const { inicio, fim } = intervaloSemanal(filtros);
  return registros.filter(
    (r) => r.semana_epidemiologica >= inicio && r.semana_epidemiologica <= fim,
  );
}

/** Uma população anual por município. Referências conflitantes ou ausentes impedem a taxa. */
export function populacaoDoRecorte(registros: RegistroSemanal[]): number | null {
  const grupos = new Map<string, Set<number>>();
  for (const r of registros) {
    const valores = grupos.get(r.codigo_ibge) ?? new Set<number>();
    if (r.populacao !== null && r.populacao > 0) valores.add(r.populacao);
    grupos.set(r.codigo_ibge, valores);
  }
  if (!grupos.size || [...grupos.values()].some((g) => g.size !== 1)) return null;
  return [...grupos.values()].reduce((soma, g) => soma + [...g][0], 0);
}

export function resumirIndicadores(registros: RegistroSemanal[]) {
  const resumo = resumirRegistros(registros);
  const populacao = populacaoDoRecorte(registros);
  return {
    ...resumo,
    populacao,
    taxa: resumo.total !== null && populacao ? (resumo.total / populacao) * 100_000 : null,
  };
}

export function indicadoresPorMunicipio(registros: RegistroSemanal[]) {
  const grupos = new Map<string, RegistroSemanal[]>();
  for (const r of registros) grupos.set(r.codigo_ibge, [...(grupos.get(r.codigo_ibge) ?? []), r]);
  return ranquearMunicipios(registros).map((m) => ({
    ...m,
    taxa: resumirIndicadores(grupos.get(m.codigo)!).taxa,
  }));
}

export type IndicadorMunicipal = ReturnType<typeof indicadoresPorMunicipio>[number];
export const SENSORES = {
  temperatura: {
    campo: 'temperatura_media_c',
    cobertura: 'cobertura_temperatura_pct',
    nome: 'Temperatura média',
    unidade: '°C',
  },
  chuva: {
    campo: 'precipitacao_mm',
    cobertura: 'cobertura_precipitacao_pct',
    nome: 'Chuva observada',
    unidade: 'mm',
  },
  umidade: {
    campo: 'umidade_media_pct',
    cobertura: 'cobertura_umidade_pct',
    nome: 'Umidade média',
    unidade: '%',
  },
} as const;
export type Sensor = keyof typeof SENSORES;

/** Sem interpolar lacunas ou misturar medições de municípios/estações diferentes. */
export function serieClimatica(registros: RegistroSemanal[], sensor: Sensor, coberturaMinima = 80) {
  if (new Set(registros.map((r) => r.codigo_ibge)).size !== 1) return [];
  const config = SENSORES[sensor];
  return registros
    .map((r) => ({
      semana: r.semana_epidemiologica,
      inicio: r.data_inicio,
      fim: r.data_fim,
      cobertura: r[config.cobertura],
      valor:
        r[config.campo] !== null &&
        r[config.cobertura] !== null &&
        r[config.cobertura]! >= coberturaMinima
          ? r[config.campo]
          : null,
    }))
    .sort((a, b) => a.semana - b.semana);
}

export function resumirSensor(registros: RegistroSemanal[], sensor: Sensor, coberturaMinima = 80) {
  const valores = serieClimatica(registros, sensor, coberturaMinima).flatMap((s) =>
    s.valor === null ? [] : [s.valor],
  );
  const soma = valores.reduce((s, v) => s + v, 0);
  return {
    valor: valores.length ? (sensor === 'chuva' ? soma : soma / valores.length) : null,
    semanas: valores.length,
  };
}
