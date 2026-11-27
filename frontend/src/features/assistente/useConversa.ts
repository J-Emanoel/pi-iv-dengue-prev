import { useEffect, useRef, useState } from 'react';
import { ErroApi, perguntarAssistente } from '../../services/api';
import type { Fonte, MensagemHistorico, RespostaAssistente } from '../../types/api';

const LIMITE_API = 2000;

function prefixoMunicipio(nomeMunicipio: string): string {
  return nomeMunicipio ? `Município de referência: ${nomeMunicipio}.\n\n` : '';
}

export function limiteDaPergunta(nomeMunicipio: string): number {
  return Math.max(0, LIMITE_API - prefixoMunicipio(nomeMunicipio).length);
}

export function perguntaComMunicipio(pergunta: string, nomeMunicipio: string): string {
  return prefixoMunicipio(nomeMunicipio) + pergunta.trim();
}

interface Turno {
  pergunta: string;
  perguntaEnviada: string;
  municipio: string;
  resposta: RespostaAssistente;
}

/** Estado da conversa separado da apresentação. Nenhum envio ocorre por efeito. */
export function useConversa(
  fonte: Fonte,
  codigoMunicipio: string,
  nomeMunicipio: string,
  habilitado: boolean,
) {
  const [turnos, setTurnos] = useState<Turno[]>([]);
  const [pergunta, setPergunta] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [espera, setEspera] = useState(0);
  const controle = useRef<AbortController | null>(null);

  function limparConversa() {
    controle.current?.abort();
    controle.current = null;
    setTurnos([]);
    setPergunta('');
    setErro(null);
    setEnviando(false);
  }

  useEffect(() => {
    limparConversa();
    return () => controle.current?.abort();
  }, [fonte, codigoMunicipio]);

  useEffect(() => {
    if (!espera) return;
    const timer = setTimeout(() => setEspera((valor) => Math.max(0, valor - 1)), 1000);
    return () => clearTimeout(timer);
  }, [espera]);

  async function enviar() {
    const texto = pergunta.trim();
    if (!texto || controle.current || !habilitado || espera > 0) return;
    const perguntaEnviada = perguntaComMunicipio(texto, nomeMunicipio);
    if (perguntaEnviada.length > LIMITE_API) {
      setErro('Sua pergunta ficou muito longa. Reduza um pouco o texto antes de enviar.');
      return;
    }
    const requisicao = new AbortController();
    controle.current = requisicao;
    const historico: MensagemHistorico[] = turnos.slice(-4).flatMap((turno) => [
      { role: 'user', content: turno.perguntaEnviada },
      { role: 'assistant', content: turno.resposta.resposta.slice(0, LIMITE_API) },
    ]);
    setEnviando(true);
    setErro(null);
    try {
      const resposta = await perguntarAssistente(
        perguntaEnviada,
        fonte,
        historico,
        requisicao.signal,
      );
      if (requisicao.signal.aborted) return;
      setTurnos((anteriores) => [
        ...anteriores,
        { pergunta: texto, perguntaEnviada, municipio: nomeMunicipio, resposta },
      ]);
      setPergunta('');
    } catch (falha) {
      if (!requisicao.signal.aborted && falha instanceof ErroApi && falha.retryAfterSeconds)
        setEspera(falha.retryAfterSeconds);
      if (!requisicao.signal.aborted)
        setErro(falha instanceof Error ? falha.message : 'Não foi possível obter a resposta.');
    } finally {
      if (!requisicao.signal.aborted) {
        controle.current = null;
        setEnviando(false);
      }
    }
  }

  return {
    turnos,
    pergunta,
    setPergunta,
    enviando,
    erro,
    espera,
    enviar,
    limparConversa,
    limite: limiteDaPergunta(nomeMunicipio),
  };
}
