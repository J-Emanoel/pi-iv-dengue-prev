import { ChevronDown, Database } from 'lucide-react';
import { useId } from 'react';
import { FONTES } from '../lib/formatacao';
import { intervaloSemanal, semanasNoAno } from '../lib/filtros';
import type { FiltrosDados, Fonte, Municipio } from '../types/api';

export interface PropriedadesFiltros {
  filtros: FiltrosDados;
  atualizar: (filtros: FiltrosDados) => void;
  municipios: Municipio[];
  cadastroIndisponivel: boolean;
  modo?: 'historico' | 'previsao' | 'assistente' | 'comparacao';
  desabilitado?: boolean;
}

const ORIENTACOES = {
  historico: 'Os resultados se atualizam automaticamente ao mudar o município ou o ano.',
  previsao: 'O período da previsão depende dos dados disponíveis. Ele aparece junto do resultado.',
  assistente:
    'O município escolhido acompanha sua pergunta. Para assuntos gerais, deixe todos os municípios.',
  comparacao: 'As cidades são comparadas na mesma fonte e nas semanas observadas em comum.',
};

export function SeletorMunicipio({
  id,
  rotulo,
  valor,
  municipios,
  selecionar,
  permitirTodos = false,
  cadastroIndisponivel = false,
  classe = '',
}: {
  id: string;
  rotulo: string;
  valor: string;
  municipios: Municipio[];
  selecionar: (codigo: string) => void;
  permitirTodos?: boolean;
  cadastroIndisponivel?: boolean;
  classe?: string;
}) {
  return (
    <div className={`field ${classe}`}>
      <label htmlFor={id}>{rotulo}</label>
      <select id={id} value={valor} onChange={(evento) => selecionar(evento.target.value)}>
        {permitirTodos && <option value="">Todos os municípios do Espírito Santo</option>}
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
  );
}

export function Filtros({
  filtros,
  atualizar,
  municipios,
  cadastroIndisponivel,
  modo = 'historico',
  desabilitado = false,
}: PropriedadesFiltros) {
  const id = useId();
  const mostrarAno = modo === 'historico' || modo === 'comparacao';
  const { inicio, fim, maximo } = intervaloSemanal(filtros);
  const fonte = FONTES[filtros.fonte];
  const anos = Array.from(
    { length: fonte.anoFinal - 2019 },
    (_, indice) => fonte.anoFinal - indice,
  );
  const vitoria = municipios.find((municipio) => municipio.codigo_ibge === '320530');

  function mudarFonte(base: Fonte) {
    atualizar({
      ...filtros,
      fonte: base,
      ano: FONTES[base].anoFinal,
      semanaInicial: undefined,
      semanaFinal: undefined,
    });
  }

  return (
    <section className="filter-bar" aria-labelledby={`${id}-titulo`}>
      <div className="filter-intro">
        <div>
          <h2 id={`${id}-titulo`}>
            {modo === 'comparacao'
              ? 'Período da comparação'
              : mostrarAno
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
          {modo !== 'comparacao' && (
            <SeletorMunicipio
              id={`${id}-municipio`}
              rotulo={modo === 'assistente' ? 'Município de referência (opcional)' : 'Município'}
              valor={filtros.codigoMunicipio}
              municipios={municipios}
              selecionar={(codigo) => atualizar({ ...filtros, codigoMunicipio: codigo })}
              permitirTodos
              cadastroIndisponivel={cadastroIndisponivel}
              classe="municipality-field"
            />
          )}
          {mostrarAno && (
            <div className="field year-field">
              <label htmlFor={`${id}-ano`}>Ano dos registros</label>
              <select
                id={`${id}-ano`}
                value={filtros.ano}
                onChange={(evento) =>
                  atualizar({
                    ...filtros,
                    ano: Number(evento.target.value),
                    semanaInicial: undefined,
                    semanaFinal: undefined,
                  })
                }
              >
                {anos.map((ano) => (
                  <option key={ano}>{ano}</option>
                ))}
              </select>
            </div>
          )}
          {mostrarAno && (
            <>
              <div className="field week-field">
                <label htmlFor={`${id}-de`}>Da semana</label>
                <select
                  id={`${id}-de`}
                  value={inicio}
                  onChange={(e) =>
                    atualizar({
                      ...filtros,
                      semanaInicial: Number(e.target.value),
                      semanaFinal: Math.max(Number(e.target.value), fim),
                    })
                  }
                >
                  {Array.from({ length: maximo }, (_, i) => (
                    <option key={i + 1} value={i + 1}>
                      {i + 1}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field week-field">
                <label htmlFor={`${id}-ate`}>Até a semana</label>
                <select
                  id={`${id}-ate`}
                  value={fim}
                  onChange={(e) =>
                    atualizar({
                      ...filtros,
                      semanaFinal: Number(e.target.value),
                      semanaInicial: Math.min(inicio, Number(e.target.value)),
                    })
                  }
                >
                  {Array.from({ length: semanasNoAno(filtros.ano) }, (_, i) => (
                    <option key={i + 1} value={i + 1}>
                      {i + 1}
                    </option>
                  ))}
                </select>
              </div>
            </>
          )}
          {filtros.codigoMunicipio && modo !== 'comparacao' && (
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
