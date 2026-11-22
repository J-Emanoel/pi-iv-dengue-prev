import { BookOpen, MessagesSquare } from 'lucide-react';
import Markdown from 'react-markdown';
import { formatarNumero, urlExternaSegura } from '../../lib/formatacao';
import type { RespostaAssistente } from '../../types/api';

const NOMES_CONSULTAS: Record<string, string> = {
  listar_municipios: 'Cadastro municipal',
  consultar_historico: 'Histórico de registros',
  comparar_municipios: 'Comparação municipal',
  consultar_modelo: 'Método e avaliação',
  consultar_previsao: 'Estimativas',
  consultar_documentos: 'Documentos oficiais',
};

export function MensagemResposta({ resposta }: { resposta: RespostaAssistente }) {
  return (
    <article className="assistant-message">
      <div className="message-author">
        <span className="assistant-avatar">
          <MessagesSquare size={17} aria-hidden="true" />
        </span>
        <strong>DenguePrev</strong>
        <span>Assistente de dados</span>
      </div>
      <div className="markdown-response">
        <Markdown
          skipHtml
          unwrapDisallowed
          allowedElements={[
            'p',
            'ul',
            'ol',
            'li',
            'strong',
            'em',
            'blockquote',
            'code',
            'h3',
            'h4',
            'br',
          ]}
        >
          {resposta.resposta}
        </Markdown>
      </div>
      {resposta.referencias.length > 0 && (
        <div className="references">
          <h3>
            <BookOpen size={15} />
            Referências desta resposta
          </h3>
          {resposta.referencias.map((referencia) => (
            <a
              key={referencia.id}
              className="reference-card"
              href={urlExternaSegura(referencia.url)}
              target="_blank"
              rel="noopener noreferrer"
            >
              <span className="reference-id">[{referencia.id}]</span>
              <div>
                <strong>{referencia.titulo}</strong>
                <small>
                  {referencia.orgao} · {referencia.ano} · página {referencia.pagina_impressa}
                </small>
              </div>
              <span className="reference-action">
                Ver página<span className="sr-only"> em outra aba</span>
              </span>
            </a>
          ))}
        </div>
      )}
      <div className="response-meta">
        <span>{resposta.modelo_llm}</span>
        {resposta.uso && (
          <span>
            {resposta.uso.chamadas_api} chamada(s) · {formatarNumero(resposta.uso.tokens_total)}{' '}
            tokens informados
          </span>
        )}
      </div>
      {resposta.consultas.length > 0 && (
        <details className="consultation-details">
          <summary>Consultas utilizadas ({resposta.consultas.length})</summary>
          <ul>
            {resposta.consultas.map((consulta, indice) => (
              <li key={indice}>
                {NOMES_CONSULTAS[consulta.ferramenta] || 'Consulta ao projeto'} ·{' '}
                {consulta.sucesso ? 'Concluída' : 'Sem resultado válido'}
              </li>
            ))}
          </ul>
        </details>
      )}
    </article>
  );
}
