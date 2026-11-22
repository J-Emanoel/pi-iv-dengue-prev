import { ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';
import { formatarNumero } from '../../lib/formatacao';
import type { MunicipioResumido } from './resumo';

export function RankingMunicipios({ municipios }: { municipios: MunicipioResumido[] }) {
  const [expandido, setExpandido] = useState(false);
  const exibidos = expandido ? municipios : municipios.slice(0, 6);
  const maximo = Math.max(1, ...municipios.map((municipio) => municipio.registros ?? 0));
  return (
    <>
      <ol className="ranking-list">
        {exibidos.map((municipio, indice) => (
          <li key={municipio.codigo}>
            <span className="ranking-position">{indice + 1}</span>
            <div className="ranking-municipality">
              <span>{municipio.nome}</span>
              <div className="ranking-track">
                <i style={{ width: `${(100 * (municipio.registros ?? 0)) / maximo}%` }} />
              </div>
              <small>
                {municipio.semanasObservadas} de {municipio.semanasNoRecorte} semanas com dados
              </small>
            </div>
            <strong>{formatarNumero(municipio.registros)}</strong>
          </li>
        ))}
      </ol>
      {municipios.length > 6 && (
        <button className="text-button ranking-toggle" onClick={() => setExpandido(!expandido)}>
          {expandido ? 'Mostrar os primeiros' : `Ver os ${municipios.length} municípios`}
          {expandido ? <ChevronUp size={17} /> : <ChevronDown size={17} />}
        </button>
      )}
    </>
  );
}
