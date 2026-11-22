import { useState } from 'react';
import {
  Line,
  LineChart,
  CartesianGrid,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
} from 'recharts';
import { Painel } from '../../components/Painel';
import { formatarData, formatarNumero, urlExternaSegura } from '../../lib/formatacao';
import type { RegistroSemanal } from '../../types/api';
import { resumirIndicadores, resumirSensor, serieClimatica, SENSORES } from './analise';
import type { Sensor } from './analise';

export function IndicadoresContexto({
  registros,
  municipioSelecionado,
  selecionarExemplo,
}: {
  registros: RegistroSemanal[];
  municipioSelecionado: boolean;
  selecionarExemplo: () => void;
}) {
  const [sensor, escolherSensor] = useState<Sensor>('temperatura');
  const [coberturaMinima, mudarCobertura] = useState(80);
  const resumo = resumirIndicadores(registros);
  const referencia = registros.find((r) => r.populacao !== null);
  const estacao = registros.find((r) => r.codigo_estacao);
  const serie = serieClimatica(registros, sensor, coberturaMinima);
  const config = SENSORES[sensor];
  return (
    <div className="context-panels">
      <Painel
        titulo="População e registros por habitante"
        descricao="O denominador é anual e não é somado novamente a cada semana."
      >
        <dl className="context-indicators">
          <div>
            <dt>População de referência</dt>
            <dd>
              {formatarNumero(resumo.populacao)} <small>habitantes</small>
            </dd>
          </div>
          <div>
            <dt>Registros observados por 100 mil habitantes</dt>
            <dd>{formatarNumero(resumo.taxa, 2)}</dd>
          </div>
        </dl>
        <p className="panel-footnote">
          A taxa usa a soma observada no intervalo selecionado. Lacunas podem reduzir o numerador; o
          indicador não é incidência de casos confirmados nem ajusta diferenças de cobertura.
        </p>
        {resumo.populacao === null && (
          <p className="panel-footnote">
            A população e a taxa ficam indisponíveis quando falta uma referência anual única para
            algum município da seleção.
          </p>
        )}
        {municipioSelecionado && referencia && (
          <p className="panel-footnote">
            Referência populacional: {formatarData(referencia.data_referencia_populacao)} ·{' '}
            {referencia.tipo_populacao || 'Tipo não informado'}.
            {referencia.fonte_populacao_url && (
              <a
                className="source-link"
                href={urlExternaSegura(referencia.fonte_populacao_url)}
                target="_blank"
                rel="noopener noreferrer"
              >
                Consultar fonte IBGE<span className="sr-only"> em outra aba</span>
              </a>
            )}
          </p>
        )}
      </Painel>
      <Painel
        titulo="Clima associado ao município"
        descricao="Chuva, temperatura e umidade da estação vinculada ao município."
      >
        {!municipioSelecionado ? (
          <div className="climate-empty">
            <p>
              Selecione uma cidade no mapa ou nos filtros para explorar o clima. Estações podem
              atender vários municípios; suas medições não são somadas como um total estadual.
            </p>
            <button className="button secondary" onClick={selecionarExemplo}>
              Explorar o clima de Vitória
            </button>
          </div>
        ) : (
          <>
            <div className="climate-controls">
              <div className="field">
                <label htmlFor="sensor-clima">Indicador climático</label>
                <select
                  id="sensor-clima"
                  value={sensor}
                  onChange={(e) => escolherSensor(e.target.value as Sensor)}
                >
                  {Object.entries(SENSORES).map(([chave, valor]) => (
                    <option key={chave} value={chave}>
                      {valor.nome} ({valor.unidade})
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="cobertura-clima">Cobertura mínima por sensor</label>
                <select
                  id="cobertura-clima"
                  value={coberturaMinima}
                  onChange={(e) => mudarCobertura(Number(e.target.value))}
                >
                  <option value="0">Sem limiar mínimo</option>
                  <option value="50">50% das horas</option>
                  <option value="80">80% das horas</option>
                  <option value="100">100% das horas</option>
                </select>
              </div>
            </div>
            <dl className="climate-indicators">
              {(Object.keys(SENSORES) as Sensor[]).map((s) => {
                const dado = resumirSensor(registros, s, coberturaMinima);
                return (
                  <div key={s}>
                    <dt>
                      {SENSORES[s].nome}
                      {s === 'chuva' ? ' (acumulado)' : ''}
                    </dt>
                    <dd>
                      {formatarNumero(dado.valor, 1)} <small>{SENSORES[s].unidade}</small>
                    </dd>
                    <span>
                      {dado.semanas} de {registros.length} semanas com dados no critério
                    </span>
                  </div>
                );
              })}
            </dl>
            {!serie.some((s) => s.valor !== null) && (
              <p className="data-legend" role="status">
                Não há observações para este sensor no critério escolhido. Confira a tabela, altere
                o período ou ajuste a cobertura mínima.
              </p>
            )}
            <div
              className="chart-container climate-chart"
              role="region"
              aria-label={`Gráfico de ${config.nome.toLowerCase()}`}
            >
              <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                <LineChart
                  data={serie}
                  margin={{ top: 15, right: 15, left: 0, bottom: 5 }}
                  accessibilityLayer
                >
                  <CartesianGrid stroke="var(--line)" strokeDasharray="3 4" vertical={false} />
                  <XAxis
                    dataKey="semana"
                    tickFormatter={(s: number) => `Sem. ${s}`}
                    minTickGap={30}
                    tick={{ fill: 'var(--muted)', fontSize: 13 }}
                  />
                  <YAxis
                    width={55}
                    tick={{ fill: 'var(--muted)', fontSize: 13 }}
                    tickFormatter={(v: number) => formatarNumero(v, 1)}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      const ponto = payload?.[0]?.payload as (typeof serie)[number] | undefined;
                      return active && ponto ? (
                        <div className="chart-tooltip">
                          <strong>
                            Semana {ponto.semana} · {formatarData(ponto.inicio, true)}–
                            {formatarData(ponto.fim, true)}
                          </strong>
                          <p>
                            {formatarNumero(ponto.valor, 1)} {config.unidade}
                          </p>
                          <small>Cobertura: {formatarNumero(ponto.cobertura, 1)}%</small>
                        </div>
                      ) : null;
                    }}
                  />
                  <Line
                    dataKey="valor"
                    name={config.nome}
                    stroke="var(--violet)"
                    strokeWidth={2}
                    dot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="panel-footnote">
              {estacao?.nome_estacao || 'Estação não informada'}
              {estacao?.distancia_km != null
                ? ` · ${formatarNumero(estacao.distancia_km, 1)} km do centroide municipal`
                : ''}
              . O limiar é exploratório e não comprova representatividade meteorológica. Médias
              resumem as médias semanais aceitas; chuva soma apenas as semanas aceitas.
            </p>
            <details className="consultation-details">
              <summary>Ver valores climáticos em tabela</summary>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Semana</th>
                      <th>Período</th>
                      <th className="numeric">
                        {config.nome} ({config.unidade})
                      </th>
                      <th className="numeric">Cobertura do sensor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {serie.map((s) => (
                      <tr key={s.semana}>
                        <td>{s.semana}</td>
                        <td>
                          {formatarData(s.inicio, true)}–{formatarData(s.fim, true)}
                        </td>
                        <td className="numeric">{formatarNumero(s.valor, 1)}</td>
                        <td className="numeric">{formatarNumero(s.cobertura, 1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </>
        )}
      </Painel>
    </div>
  );
}
