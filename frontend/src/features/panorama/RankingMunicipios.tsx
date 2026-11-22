import { ChevronDown, ChevronUp } from 'lucide-react';
import { useId, useState } from 'react';
import { formatarNumero } from '../../lib/formatacao';
import type { MunicipioResumido } from './resumo';

export function RankingMunicipios({
  municipios,
  selecionar,
}: {
  municipios: MunicipioResumido[];
  selecionar?: (codigo: string) => void;
}) {
  const [expandido, setExpandido] = useState(false);
  const [busca, buscar] = useState('');
  const id = useId();
  const normalizar = (s: string) =>
    s
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLocaleLowerCase('pt-BR');
  const encontrados = municipios
    .map((m, i) => ({ ...m, posicao: i + 1 }))
    .filter((m) => normalizar(m.nome).includes(normalizar(busca.trim())));
  const exibidos = expandido || busca ? encontrados : encontrados.slice(0, 6);
  const maximo = Math.max(1, ...municipios.map((municipio) => municipio.registros ?? 0));
  return (
    <>
      <div className="field ranking-search">
        <label htmlFor={id}>Buscar município no ranking</label>
        <input
          id={id}
          type="search"
          value={busca}
          onChange={(e) => buscar(e.target.value)}
          placeholder="Digite o nome da cidade"
        />
      </div>
      {!encontrados.length && <p role="status">Nenhum município encontrado para essa busca.</p>}
      <ol className="ranking-list">
        {exibidos.map((municipio) => (
          <li key={municipio.codigo}>
            <span className="ranking-position">{municipio.posicao}</span>
            <div className="ranking-municipality">
              {selecionar ? (
                <button className="ranking-city-link" onClick={() => selecionar(municipio.codigo)}>
                  {municipio.nome}
                </button>
              ) : (
                <span>{municipio.nome}</span>
              )}
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
      {encontrados.length > 6 && !busca && (
        <button className="text-button ranking-toggle" onClick={() => setExpandido(!expandido)}>
          {expandido ? 'Mostrar os primeiros' : `Ver os ${municipios.length} municípios`}
          {expandido ? <ChevronUp size={17} /> : <ChevronDown size={17} />}
        </button>
      )}
    </>
  );
}
