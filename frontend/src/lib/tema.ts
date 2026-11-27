export type Tema = 'light' | 'dark';

export const CHAVE_TEMA = 'dengueprev-theme';

export function temaValido(valor: unknown): valor is Tema {
  return valor === 'light' || valor === 'dark';
}

/** Usa a escolha salva, se válida; caso contrário, segue a preferência do sistema. */
export function resolverTema(salvo: unknown, sistemaEscuro: boolean): Tema {
  if (temaValido(salvo)) return salvo;
  return sistemaEscuro ? 'dark' : 'light';
}

export function alternarTema(atual: Tema): Tema {
  return atual === 'dark' ? 'light' : 'dark';
}
