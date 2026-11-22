import { useId } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { formatarData, formatarNumero } from '../../lib/formatacao';
import type { SemanaResumida } from './resumo';

export function GraficoSemanal({ semanas }: { semanas: SemanaResumida[] }) {
  const gradiente = useId().replaceAll(':', '');
  return (
    <div
      className="chart-container"
      role="region"
      aria-label="Gráfico de registros observados por semana epidemiológica"
    >
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <AreaChart
          data={semanas}
          margin={{ top: 20, right: 14, bottom: 2, left: 0 }}
          accessibilityLayer
        >
          <defs>
            <linearGradient id={gradiente} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--chart)" stopOpacity={0.2} />
              <stop offset="95%" stopColor="var(--chart)" stopOpacity={0.02} />
            </linearGradient>
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
            tickFormatter={(valor: number) => formatarNumero(valor)}
            width={65}
            tickLine={false}
            axisLine={false}
            tick={{ fill: 'var(--muted)', fontSize: 13 }}
          />
          <Tooltip
            content={({ active, payload }) => {
              const semana = payload?.[0]?.payload as SemanaResumida | undefined;
              return active && semana ? (
                <div className="chart-tooltip">
                  <strong>
                    Semana {semana.semana} · {formatarData(semana.inicio, true)}–
                    {formatarData(semana.fim, true)}
                  </strong>
                  <p>{formatarNumero(semana.registros)} registros observados</p>
                  <small>
                    {semana.municipiosObservados} de {semana.municipiosNoRecorte} municípios com
                    observação
                  </small>
                </div>
              ) : null;
            }}
          />
          <Area
            type="linear"
            dataKey="registros"
            name="Registros observados"
            connectNulls={false}
            stroke="var(--chart)"
            strokeWidth={2.5}
            fill={`url(#${gradiente})`}
            activeDot={{ r: 5, stroke: '#fff', strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
