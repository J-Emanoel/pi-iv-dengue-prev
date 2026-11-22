import { FONTES } from './formatacao';
import type { FiltrosDados, Fonte } from '../types/api';

/** Mesmo calendário do backend: domingo a sábado; primeira semana com pelo menos quatro dias. */
export function semanasNoAno(ano: number): number {
  function inicio(a: number) {
    const quatro = new Date(Date.UTC(a, 0, 4));
    return quatro.getTime() - quatro.getUTCDay() * 86_400_000;
  }
  return (inicio(ano + 1) - inicio(ano)) / (7 * 86_400_000);
}

export function intervaloSemanal(filtros: FiltrosDados) {
  const maximo = semanasNoAno(filtros.ano);
  const inicio = Math.max(1, Math.min(maximo, filtros.semanaInicial ?? 1));
  const fim = Math.max(inicio, Math.min(maximo, filtros.semanaFinal ?? maximo));
  return { inicio, fim, maximo };
}

export function lerFiltros(params: URLSearchParams): FiltrosDados {
  const fonte: Fonte = params.get('fonte') === 'sesa' ? 'sesa' : 'sinan';
  const solicitado = Number(params.get('ano'));
  const ano =
    Number.isInteger(solicitado) && solicitado >= 2020 && solicitado <= FONTES[fonte].anoFinal
      ? solicitado
      : FONTES[fonte].anoFinal;
  const inteiro = (campo: string) => {
    const valor = Number(params.get(campo));
    return Number.isInteger(valor) && valor >= 1 && valor <= semanasNoAno(ano) ? valor : undefined;
  };
  const filtros: FiltrosDados = {
    fonte,
    ano,
    codigoMunicipio: /^32\d{4}$/.test(params.get('municipio') ?? '')
      ? params.get('municipio')!
      : '',
    compararCom: /^32\d{4}$/.test(params.get('comparar') ?? '')
      ? params.get('comparar')!
      : undefined,
    semanaInicial: inteiro('de'),
    semanaFinal: inteiro('ate'),
  };
  const { inicio, fim } = intervaloSemanal(filtros);
  return { ...filtros, semanaInicial: inicio, semanaFinal: fim };
}

export function parametrosFiltros(filtros: FiltrosDados): URLSearchParams {
  const { inicio, fim } = intervaloSemanal(filtros);
  const params = new URLSearchParams({ fonte: filtros.fonte, ano: String(filtros.ano) });
  if (filtros.codigoMunicipio) params.set('municipio', filtros.codigoMunicipio);
  if (filtros.compararCom) params.set('comparar', filtros.compararCom);
  if (inicio !== 1) params.set('de', String(inicio));
  if (fim !== semanasNoAno(filtros.ano)) params.set('ate', String(fim));
  return params;
}
