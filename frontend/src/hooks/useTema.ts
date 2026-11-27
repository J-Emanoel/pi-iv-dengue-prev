import { useCallback, useEffect, useState } from 'react';
import { CHAVE_TEMA, alternarTema, resolverTema, temaValido, type Tema } from '../lib/tema';

const CORES_BARRA: Record<Tema, string> = { light: '#2856e8', dark: '#0e1220' };

function lerSalvo(): string | null {
  try {
    return localStorage.getItem(CHAVE_TEMA);
  } catch {
    return null;
  }
}

function sistemaPrefereEscuro(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: dark)').matches;
}

function temaAplicado(): Tema {
  const atual = document.documentElement.dataset.theme;
  return temaValido(atual) ? atual : resolverTema(lerSalvo(), sistemaPrefereEscuro());
}

export function useTema() {
  const [tema, setTema] = useState<Tema>(temaAplicado);

  useEffect(() => {
    document.documentElement.dataset.theme = tema;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', CORES_BARRA[tema]);
  }, [tema]);

  const alternar = useCallback(() => {
    setTema((atual) => {
      const novo = alternarTema(atual);
      try {
        localStorage.setItem(CHAVE_TEMA, novo);
      } catch {
        /* armazenamento indisponível: a escolha vale apenas nesta sessão */
      }
      return novo;
    });
  }, []);

  return { tema, alternar };
}
