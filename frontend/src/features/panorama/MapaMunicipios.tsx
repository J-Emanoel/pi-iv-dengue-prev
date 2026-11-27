import { useState } from 'react';
import { Painel } from '../../components/Painel';
import { formatarNumero } from '../../lib/formatacao';
import type { IndicadorMunicipal } from './analise';
import { corDoMapa, fonteMalha, municipiosNoMapa } from './geografia';

export function MapaMunicipios({
  indicadores,
  selecionado,
  selecionar,
}: {
  indicadores: IndicadorMunicipal[];
  selecionado: string;
  selecionar: (codigo: string) => void;
}) {
  const [medida, mudarMedida] = useState<'registros' | 'taxa'>('registros');
  const [ativo, ativar] = useState('');
  const porCodigo = new Map(indicadores.map((i) => [i.codigo, i]));
  const maximo = Math.max(0, ...indicadores.map((i) => i[medida] ?? 0));
  const detalhe = porCodigo.get(ativo || selecionado);
  const unidade = medida === 'taxa' ? 'registros por 100 mil habitantes' : 'registros';
  return (
    <Painel
      titulo="Explore os municípios"
      descricao="Clique em uma cidade para selecioná-la. Histórico, população e clima acompanham essa escolha."
    >
      <div className="segmented-control" role="group" aria-label="Indicador do mapa">
        <button aria-pressed={medida === 'registros'} onClick={() => mudarMedida('registros')}>
          Registros
        </button>
        <button aria-pressed={medida === 'taxa'} onClick={() => mudarMedida('taxa')}>
          Por 100 mil habitantes
        </button>
      </div>
      <div className="map-layout">
        <svg
          className="municipality-map"
          viewBox="0 0 360 460"
          role="group"
          aria-label="Mapa dos municípios do Espírito Santo"
        >
          <defs>
            <pattern id="sem-observacao" patternUnits="userSpaceOnUse" width="6" height="6">
              <rect width="6" height="6" className="map-hatch-bg" />
              <path d="M0 6L6 0" className="map-hatch-line" strokeWidth="1" />
            </pattern>
          </defs>
          {municipiosNoMapa.map((m) => {
            const dado = porCodigo.get(m.codigo);
            const valor = dado?.[medida] ?? null;
            const nome = dado?.nome || m.codigo;
            return (
              <path
                key={m.codigo}
                d={m.caminho}
                fill={corDoMapa(valor, maximo)}
                fillRule="evenodd"
                className={m.codigo === selecionado ? 'selected-municipality' : ''}
                role="button"
                tabIndex={0}
                aria-label={`${nome}: ${valor === null ? 'valor indisponível' : formatarNumero(valor, medida === 'taxa' ? 2 : 0) + ' ' + unidade}`}
                aria-pressed={m.codigo === selecionado}
                onMouseEnter={() => ativar(m.codigo)}
                onMouseLeave={() => ativar('')}
                onFocus={() => ativar(m.codigo)}
                onBlur={() => ativar('')}
                onClick={() => selecionar(m.codigo)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    selecionar(m.codigo);
                  }
                }}
              >
                <title>{nome}</title>
              </path>
            );
          })}
        </svg>
        <div className="map-reading" aria-live="polite">
          {detalhe ? (
            <>
              <strong>{detalhe.nome}</strong>
              <span className="map-value">
                {formatarNumero(detalhe[medida], medida === 'taxa' ? 2 : 0)}
              </span>
              <span>{unidade}</span>
              <p>
                {detalhe.semanasObservadas} de {detalhe.semanasNoRecorte} semanas com observação.
              </p>
              <button className="text-button" onClick={() => selecionar(detalhe.codigo)}>
                Selecionar município
              </button>
            </>
          ) : (
            <>
              <strong>Espírito Santo</strong>
              <p>
                Passe sobre uma área ou navegue pelo mapa com a tecla Tab para consultar os valores.
              </p>
            </>
          )}
          <div className="map-scale">
            <span>0</span>
            <i />
            <span>{formatarNumero(maximo, medida === 'taxa' ? 2 : 0)}</span>
          </div>
          <p className="map-missing">
            <i /> Hachurado: sem observação ou denominador disponível.
          </p>
        </div>
      </div>
      <p className="panel-footnote">
        Valores do intervalo selecionado, com cobertura variável. A cor não representa risco nem
        incidência de casos confirmados.
      </p>
      <a className="source-link" href={fonteMalha} target="_blank" rel="noopener noreferrer">
        Malha municipal simplificada · IBGE<span className="sr-only">, abre em outra aba</span>
      </a>
    </Painel>
  );
}
