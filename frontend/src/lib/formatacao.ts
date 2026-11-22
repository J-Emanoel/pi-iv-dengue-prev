import type { Fonte } from '../types/api';

export const FONTES: Record<Fonte, { nome: string; referencia: string; anoFinal: number }> = {
  sinan: { nome: 'SINAN', referencia: 'Semana dos primeiros sintomas', anoFinal: 2026 },
  sesa: { nome: 'SESA/e-SUS VS', referencia: 'Semana de notificação', anoFinal: 2024 },
};

export function formatarNumero(valor: number | null | undefined, casas = 0): string {
  if (valor == null || !Number.isFinite(valor)) return '—';
  return new Intl.NumberFormat('pt-BR', { maximumFractionDigits: casas }).format(valor);
}

export function formatarData(valor: string | null | undefined, curta = false): string {
  if (!valor) return '—';
  const data = new Date(`${valor.slice(0, 10)}T12:00:00Z`);
  if (Number.isNaN(data.getTime())) return '—';
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    ...(curta ? {} : { year: 'numeric' }),
    timeZone: 'UTC',
  }).format(data);
}

export function urlExternaSegura(valor: string): string | undefined {
  try {
    const url = new URL(valor);
    return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}
