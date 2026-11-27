import { describe, expect, it } from 'vitest';
import { alternarTema, resolverTema, temaValido } from './tema';

describe('tema claro e escuro', () => {
  it('prioriza a escolha salva sobre a preferência do sistema', () => {
    expect(resolverTema('light', true)).toBe('light');
    expect(resolverTema('dark', false)).toBe('dark');
  });
  it('segue o sistema quando não há escolha válida', () => {
    expect(resolverTema(null, true)).toBe('dark');
    expect(resolverTema(undefined, false)).toBe('light');
    expect(resolverTema('azul', true)).toBe('dark');
  });
  it('alterna entre os dois temas e valida valores', () => {
    expect(alternarTema('light')).toBe('dark');
    expect(alternarTema('dark')).toBe('light');
    expect(temaValido('dark')).toBe(true);
    expect(temaValido('auto')).toBe(false);
  });
});
