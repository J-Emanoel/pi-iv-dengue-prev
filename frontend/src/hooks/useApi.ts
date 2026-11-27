import { useEffect, useState } from 'react';
import { requisitar } from '../services/api';

interface Estado<T> {
  caminho: string | null;
  dados: T | undefined;
  erro: string | null;
  carregando: boolean;
  demorado: boolean;
}

/** Cancela leituras antigas e nunca apresenta dados de outro filtro como atuais. */
export function useApi<T>(caminho: string | null) {
  const [revisao, setRevisao] = useState(0);
  const [estado, setEstado] = useState<Estado<T>>({
    caminho: null,
    dados: undefined,
    erro: null,
    carregando: false,
    demorado: false,
  });

  useEffect(() => {
    if (!caminho) return;
    const controle = new AbortController();
    setEstado({ caminho, dados: undefined, erro: null, carregando: true, demorado: false });
    const aviso = setTimeout(() => {
      setEstado((anterior) =>
        anterior.caminho === caminho && anterior.carregando
          ? { ...anterior, demorado: true }
          : anterior,
      );
    }, 8000);
    requisitar<T>(caminho, { signal: controle.signal })
      .then((dados) => {
        clearTimeout(aviso);
        if (!controle.signal.aborted)
          setEstado({ caminho, dados, erro: null, carregando: false, demorado: false });
      })
      .catch((erro: Error) => {
        clearTimeout(aviso);
        if (!controle.signal.aborted)
          setEstado({
            caminho,
            dados: undefined,
            erro: erro.message,
            carregando: false,
            demorado: false,
          });
      });
    return () => {
      clearTimeout(aviso);
      controle.abort();
    };
  }, [caminho, revisao]);

  const atual =
    estado.caminho === caminho
      ? estado
      : { caminho, dados: undefined, erro: null, carregando: Boolean(caminho), demorado: false };
  return { ...atual, recarregar: () => setRevisao((valor) => valor + 1) };
}
