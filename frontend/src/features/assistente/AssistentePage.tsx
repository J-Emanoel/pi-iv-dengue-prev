import { BookOpen, CircleHelp, Database, MessagesSquare, Plus } from 'lucide-react';
import { useEffect, useRef } from 'react';
import type { FormEvent } from 'react';
import { AjudaPagina } from '../../components/AjudaPagina';
import { Filtros } from '../../components/Filtros';
import type { PropriedadesFiltros } from '../../components/Filtros';
import { CabecalhoPagina, Painel } from '../../components/Painel';
import { useApi } from '../../hooks/useApi';
import { FONTES, urlExternaSegura } from '../../lib/formatacao';
import type { CatalogoDocumental, ConfiguracaoAssistente } from '../../types/api';
import { MensagemResposta } from './MensagemResposta';
import { useConversa } from './useConversa';

export default function AssistentePage(props: PropriedadesFiltros) {
  const { fonte, codigoMunicipio, ano } = props.filtros;
  const nomeMunicipio =
    props.municipios.find((municipio) => municipio.codigo_ibge === codigoMunicipio)?.nome ||
    codigoMunicipio;
  const configuracao = useApi<ConfiguracaoAssistente>('/assistente/status');
  const catalogo = useApi<CatalogoDocumental>('/documentos');
  const conversa = useConversa(
    fonte,
    codigoMunicipio,
    nomeMunicipio,
    Boolean(configuracao.dados?.configuracao_local_completa),
  );
  const campo = useRef<HTMLTextAreaElement>(null);
  const ultimaResposta = useRef<HTMLDivElement>(null);
  const cidadeExemplo = nomeMunicipio || 'Vitória';

  useEffect(() => {
    if (conversa.turnos.length)
      ultimaResposta.current?.scrollIntoView?.({ block: 'start', behavior: 'auto' });
  }, [conversa.turnos.length]);

  function preencherPergunta(texto: string) {
    conversa.setPergunta(texto);
    campo.current?.focus();
    campo.current?.scrollIntoView?.({ block: 'center', behavior: 'auto' });
  }

  function enviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    void conversa.enviar();
  }

  const sugestoes = [
    {
      titulo: 'Consultar uma previsão',
      descricao: `Estimativa disponível para ${cidadeExemplo}`,
      texto: `Qual é a previsão disponível para ${cidadeExemplo}? Informe o período e explique como ela foi calculada.`,
    },
    {
      titulo: 'Entender o histórico',
      descricao: `Registros de ${cidadeExemplo} em ${ano}`,
      texto: `Consulte o total de registros de ${cidadeExemplo} em ${ano}. Até quando há observações e quais são as limitações desses dados?`,
    },
    {
      titulo: 'Cuidados e prevenção',
      descricao: 'Orientações dos documentos oficiais',
      texto: 'O que posso fazer para eliminar criadouros do Aedes? Cite os documentos oficiais.',
    },
  ];

  return (
    <>
      <CabecalhoPagina
        categoria="ASSISTENTE"
        titulo="Pergunte sobre os dados"
        descricao="Escreva uma pergunta sobre dengue, uma cidade ou uma previsão. A resposta informa os dados e documentos utilizados."
        acao={
          <button
            className="button secondary"
            onClick={conversa.limparConversa}
            disabled={conversa.enviando || !conversa.turnos.length}
          >
            <Plus size={17} />
            Nova conversa
          </button>
        }
      />
      <Filtros {...props} modo="assistente" desabilitado={conversa.enviando} />
      <div className="assistant-grid">
        <section className="chat-panel panel" aria-label="Conversa com o assistente">
          <div className="chat-heading">
            <span className="assistant-avatar">
              <MessagesSquare size={21} aria-hidden="true" />
            </span>
            <div>
              <h2>Como posso ajudar?</h2>
              <p>
                {nomeMunicipio
                  ? `Perguntas sobre ${nomeMunicipio}`
                  : 'Perguntas gerais ou sobre um município'}{' '}
                · Base {FONTES[fonte].nome}
              </p>
            </div>
          </div>
          {configuracao.erro && (
            <div className="inline-error" role="alert">
              <p>{configuracao.erro}</p>
              <button className="text-button" onClick={configuracao.recarregar}>
                Verificar disponibilidade novamente
              </button>
            </div>
          )}
          {configuracao.dados && !configuracao.dados.configuracao_local_completa && (
            <div className="inline-error" role="status">
              O assistente está indisponível enquanto o serviço é configurado. Você pode consultar
              os registros na página Histórico.
            </div>
          )}
          {conversa.erro && (
            <div className="inline-error" role="alert">
              {conversa.erro}
            </div>
          )}
          <form className="chat-form" onSubmit={enviar}>
            <label htmlFor="pergunta-assistente">Sua pergunta</label>
            <p className="field-help" id="ajuda-pergunta">
              {nomeMunicipio
                ? `Incluiremos ${nomeMunicipio} como município de referência.`
                : 'Se perguntar sobre uma cidade, escreva seu nome e o período ou selecione o município acima.'}
            </p>
            <textarea
              ref={campo}
              id="pergunta-assistente"
              aria-describedby="ajuda-pergunta"
              placeholder={`Ex.: Qual é a previsão disponível para ${cidadeExemplo} e de quando são os dados?`}
              value={conversa.pergunta}
              onChange={(evento) => conversa.setPergunta(evento.target.value)}
              maxLength={conversa.limite}
              rows={3}
              disabled={conversa.enviando}
            />
            <div className="composer-actions">
              <span className="character-count">
                {conversa.pergunta.length} de {conversa.limite} caracteres
              </span>
              <button
                type="submit"
                className="button primary send-button"
                disabled={
                  !conversa.pergunta.trim() ||
                  conversa.enviando ||
                  !configuracao.dados?.configuracao_local_completa
                }
              >
                {conversa.enviando ? (
                  <>
                    <span className="spinner" />
                    Buscando resposta…
                  </>
                ) : (
                  'Enviar pergunta'
                )}
              </button>
            </div>
            <p className="composer-note">
              Cada envio utiliza a cota de IA do projeto. As sugestões apenas preenchem o campo;
              você decide quando enviar.
            </p>
          </form>
          {!conversa.turnos.length && (
            <div className="chat-suggestions">
              <h3>Você pode começar com um exemplo</h3>
              <div className="suggestion-list">
                {sugestoes.map((sugestao) => (
                  <button
                    key={sugestao.titulo}
                    onClick={() => preencherPergunta(sugestao.texto)}
                    disabled={conversa.enviando}
                  >
                    <strong>{sugestao.titulo}</strong>
                    <span>{sugestao.descricao}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="conversation" role="log" aria-live="polite" aria-relevant="additions">
            {conversa.turnos.map((turno, indice) => (
              <div
                key={indice}
                className="conversation-turn"
                ref={indice === conversa.turnos.length - 1 ? ultimaResposta : undefined}
              >
                <div className="user-message">
                  <span>Você{turno.municipio ? ` · ${turno.municipio}` : ''}</span>
                  <p>{turno.pergunta}</p>
                </div>
                <MensagemResposta resposta={turno.resposta} />
              </div>
            ))}
          </div>
          {conversa.turnos.length > 0 && (
            <div className="conversation-actions">
              <button
                className="button secondary"
                onClick={() => preencherPergunta('')}
                disabled={conversa.enviando}
              >
                Fazer outra pergunta
              </button>
            </div>
          )}
        </section>
        <aside className="assistant-aside">
          <Painel titulo="De onde vêm as respostas?">
            <div className="source-explainer">
              <Database size={21} aria-hidden="true" />
              <div>
                <h3>Registros e previsões</h3>
                <p>
                  O assistente consulta as mesmas bases e os mesmos modelos disponíveis no painel.
                </p>
              </div>
            </div>
            <div className="source-explainer">
              <BookOpen size={21} aria-hidden="true" />
              <div>
                <h3>Documentos oficiais</h3>
                <p>
                  Respostas sobre prevenção podem incluir links para a página do documento
                  utilizado.
                </p>
              </div>
            </div>
            <div className="source-explainer">
              <CircleHelp size={21} aria-hidden="true" />
              <div>
                <h3>Confira as datas</h3>
                <p>
                  A resposta deve informar a data dos dados. Informações ausentes aparecem com uma
                  explicação.
                </p>
              </div>
            </div>
          </Painel>
          <Painel
            titulo="Documentos disponíveis"
            descricao="Abra uma fonte para consultar a publicação completa."
          >
            {catalogo.carregando && (
              <p className="muted" role="status">
                Carregando os documentos…
              </p>
            )}
            {catalogo.erro && (
              <p className="muted">A lista de documentos está indisponível no momento.</p>
            )}
            {catalogo.dados?.fontes.map((documento) => (
              <a
                key={documento.id}
                className="library-link"
                href={urlExternaSegura(documento.url_pdf)}
                target="_blank"
                rel="noopener noreferrer"
              >
                <strong>{documento.titulo}</strong>
                <span>
                  {documento.orgao} · {documento.ano}
                </span>
                <span className="library-action">
                  Abrir documento<span className="sr-only"> em outra aba</span>
                </span>
              </a>
            ))}
            {catalogo.dados && (
              <p className="panel-footnote">
                Os documentos têm edição própria. Consulte o ano indicado na referência.
              </p>
            )}
          </Painel>
        </aside>
      </div>
      <AjudaPagina
        passos={[
          'Escolha um município, se a pergunta for sobre uma cidade. Essa escolha acompanha o texto enviado.',
          'Escreva sua pergunta ou escolha um exemplo. Depois clique em Enviar pergunta.',
          'Leia a resposta e abra as referências para consultar os documentos. Ao mudar o município ou a base, uma nova conversa é iniciada.',
        ]}
      />
    </>
  );
}
