import { useId } from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { formatarData, formatarNumero } from '../lib/formatacao';

export interface PontoTemporal {
  semana: number;
  inicio: string;
  fim: string;
  valores: Record<string, number | null>;
  observacao?: string;
}

interface SerieTemporal {
  chave: string;
  nome: string;
  cor: string;
  unidade?: string;
  tracejada?: boolean;
}

interface PropriedadesGrafico {
  pontos: PontoTemporal[];
  series: SerieTemporal[];
  rotulo: string;
  casasDecimais?: number;
  preenchido?: boolean;
  classe?: string;
}

/** Apresentação compartilhada; cada página prepara seus valores e critérios de cobertura. */
export function GraficoTemporal({
  pontos,
  series,
  rotulo,
  casasDecimais = 0,
  preenchido = false,
  classe = '',
}: PropriedadesGrafico) {
  const identificador = useId().replaceAll(':', '');
  return (
    <div className={`chart-container ${classe}`} role="region" aria-label={rotulo}>
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <ComposedChart
          data={pontos}
          margin={{ top: 20, right: 14, bottom: 10, left: 0 }}
          accessibilityLayer
        >
          <defs>
            {preenchido &&
              series.map((serie) => (
                <linearGradient
                  key={serie.chave}
                  id={`${identificador}-${serie.chave}`}
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop offset="0%" stopColor={serie.cor} stopOpacity={0.2} />
                  <stop offset="95%" stopColor={serie.cor} stopOpacity={0.02} />
                </linearGradient>
              ))}
          </defs>
          <CartesianGrid stroke="var(--line)" strokeDasharray="3 4" vertical={false} />
          <XAxis
            dataKey="semana"
            tickFormatter={(semana: number) => `Sem. ${semana}`}
            minTickGap={36}
            tickLine={false}
            axisLine={false}
            tick={{ fill: 'var(--muted)', fontSize: 13 }}
            dy={10}
          />
          <YAxis
            tickFormatter={(valor: number) => formatarNumero(valor, casasDecimais)}
            width={65}
            tickLine={false}
            axisLine={false}
            tick={{ fill: 'var(--muted)', fontSize: 13 }}
          />
          <Tooltip
            filterNull={false}
            content={({ active, payload }) => {
              const ponto = payload?.[0]?.payload as PontoTemporal | undefined;
              return active && ponto ? (
                <div className="chart-tooltip">
                  <strong>
                    Semana {ponto.semana} · {formatarData(ponto.inicio, true)}–
                    {formatarData(ponto.fim, true)}
                  </strong>
                  {series.map((serie) => (
                    <p key={serie.chave}>
                      {serie.nome}: {formatarNumero(ponto.valores[serie.chave], casasDecimais)}
                      {serie.unidade && ` ${serie.unidade}`}
                    </p>
                  ))}
                  {ponto.observacao && <small>{ponto.observacao}</small>}
                </div>
              ) : null;
            }}
          />
          {series.length > 1 && <Legend />}
          {series.map((serie) => {
            const propriedades = {
              type: 'linear' as const,
              dataKey: (ponto: PontoTemporal) => ponto.valores[serie.chave],
              name: serie.nome,
              stroke: serie.cor,
              strokeWidth: 2.5,
              strokeDasharray: serie.tracejada ? '6 3' : undefined,
              connectNulls: false,
              isAnimationActive: false,
            };
            return preenchido ? (
              <Area
                key={serie.chave}
                {...propriedades}
                fill={`url(#${identificador}-${serie.chave})`}
              />
            ) : (
              <Line key={serie.chave} {...propriedades} dot={false} />
            );
          })}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
