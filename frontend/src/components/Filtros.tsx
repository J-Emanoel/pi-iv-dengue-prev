import { ChevronDown, Database } from 'lucide-react';
import { useId } from 'react';
import { FONTES } from '../lib/formatacao';
import type { FiltrosDados, Fonte, Municipio } from '../types/api';

export interface PropriedadesFiltros {
  filtros: FiltrosDados;
  atualizar: (filtros: FiltrosDados) => void;
  municipios: Municipio[];
  cadastroIndisponivel: boolean;
  modo?: 'historico' | 'previsao' | 'assistente';
  desabilitado?: boolean;
}

const ORIENTACOES = {
  historico: 'Os resultados se atualizam automaticamente ao mudar o município ou o ano.',
  previsao: 'O período da previsão depende dos dados disponíveis. Ele aparece junto do resultado.',
  assistente:
    'O município escolhido acompanha sua pergunta. Para assuntos gerais, deixe todos os municípios.',
};

export function Filtros({
  filtros,
  atualizar,
  municipios,
  cadastroIndisponivel,
  modo = 'historico',
  desabilitado = false,
}: PropriedadesFiltros) {
  const id = useId();
  const mostrarAno = modo === 'historico';
  const fonte = FONTES[filtros.fonte];
  const anos = Array.from(
    { length: fonte.anoFinal - 2019 },
    (_, indice) => fonte.anoFinal - indice,
  );
  const vitoria = municipios.find((municipio) => municipio.codigo_ibge === '320530');

  function mudarFonte(base: Fonte) {
    atualizar({ ...filtros, fonte: base, ano: FONTES[base].anoFinal });
  }

  return (
    <section className="filter-bar" aria-labelledby={`${id}-titulo`}>
      <div className="filter-intro">
        <div>
          <h2 id={`${id}-titulo`}>
            {mostrarAno
              ? 'Escolha o município e o ano'
              : modo === 'assistente'
                ? 'Município da conversa'
                : 'Escolha o município'}
          </h2>
          <p>{ORIENTACOES[modo]}</p>
        </div>
        {modo === 'historico' && !filtros.codigoMunicipio && vitoria && (
          <button
            type="button"
            className="button secondary"
            disabled={desabilitado}
            onClick={() => atualizar({ ...filtros, codigoMunicipio: vitoria.codigo_ibge })}
          >
            Experimentar com Vitória
          </button>
        )}
      </div>
      <fieldset disabled={desabilitado} className="filter-controls">
        <legend className="sr-only">Selecione os dados da consulta</legend>
        <div className="filter-fields">
          <div className="field municipality-field">
            <label htmlFor={`${id}-municipio`}>
              {modo === 'assistente' ? 'Município de referência (opcional)' : 'Município'}
            </label>
            <select
              id={`${id}-municipio`}
              value={filtros.codigoMunicipio}
              onChange={(evento) => atualizar({ ...filtros, codigoMunicipio: evento.target.value })}
            >
              <option value="">Todos os municípios do Espírito Santo</option>
              {municipios.map((municipio) => (
                <option key={municipio.codigo_ibge} value={municipio.codigo_ibge}>
                  {municipio.nome}
                </option>
              ))}
            </select>
            {cadastroIndisponivel && (
              <small className="field-note">Não foi possível carregar a lista de municípios.</small>
            )}
          </div>
          {mostrarAno && (
            <div className="field year-field">
              <label htmlFor={`${id}-ano`}>Ano dos registros</label>
              <select
                id={`${id}-ano`}
                value={filtros.ano}
                onChange={(evento) => atualizar({ ...filtros, ano: Number(evento.target.value) })}
              >
                {anos.map((ano) => (
                  <option key={ano}>{ano}</option>
                ))}
              </select>
            </div>
          )}
          {filtros.codigoMunicipio && (
            <button
              type="button"
              className="text-button reset-filters"
              onClick={() => atualizar({ ...filtros, codigoMunicipio: '' })}
            >
              Ver todos os municípios
            </button>
          )}
        </div>
        <details className="source-options">
          <summary>
            <Database size={17} aria-hidden="true" />
            <span>
              Base de dados: <strong>{fonte.nome}</strong>
            </span>
            <span className="source-change-label">Alterar base</span>
            <ChevronDown size={16} aria-hidden="true" />
          </summary>
          <div className="source-options-body">
            <div className="field">
              <label htmlFor={`${id}-fonte`}>Qual base você deseja consultar?</label>
              <select
                id={`${id}-fonte`}
                value={filtros.fonte}
                onChange={(evento) => mudarFonte(evento.target.value as Fonte)}
              >
                <option value="sinan">SINAN · anos de 2020 a 2026</option>
                <option value="sesa">SESA/e-SUS VS · anos de 2020 a 2024</option>
              </select>
            </div>
            <p>
              {fonte.referencia}. As duas bases têm critérios e períodos próprios e são consultadas
              separadamente.
              {mostrarAno && ' Ao mudar a base, selecionamos o ano mais recente disponível nela.'}
            </p>
          </div>
        </details>
      </fieldset>
    </section>
  );
}
