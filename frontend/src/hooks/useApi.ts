import { useEffect, useState } from 'react';
import { requisitar } from '../services/api';

interface Estado<T> {
  caminho: string | null;
  dados: T | undefined;
  erro: string | null;
  carregando: boolean;
}

/** Cancela leituras antigas e nunca apresenta dados de outro filtro como atuais. */
export function useApi<T>(caminho: string | null) {
  const [revisao, setRevisao] = useState(0);
  const [estado, setEstado] = useState<Estado<T>>({
    caminho: null,
    dados: undefined,
    erro: null,
    carregando: false,
  });

  useEffect(() => {
    if (!caminho) return;
    const controle = new AbortController();
    setEstado({ caminho, dados: undefined, erro: null, carregando: true });
    requisitar<T>(caminho, { signal: controle.signal })
      .then((dados) => {
        if (!controle.signal.aborted) setEstado({ caminho, dados, erro: null, carregando: false });
      })
      .catch((erro: Error) => {
        if (!controle.signal.aborted)
          setEstado({ caminho, dados: undefined, erro: erro.message, carregando: false });
      });
    return () => controle.abort();
  }, [caminho, revisao]);

  const atual =
    estado.caminho === caminho
      ? estado
      : { caminho, dados: undefined, erro: null, carregando: Boolean(caminho) };
  return { ...atual, recarregar: () => setRevisao((valor) => valor + 1) };
}
