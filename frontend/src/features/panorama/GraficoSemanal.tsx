import { GraficoTemporal } from '../../components/GraficoTemporal';
import type { SemanaResumida } from './resumo';

export function GraficoSemanal({ semanas }: { semanas: SemanaResumida[] }) {
  return (
    <GraficoTemporal
      rotulo="Gráfico de registros observados por semana epidemiológica"
      preenchido
      pontos={semanas.map((semana) => ({
        semana: semana.semana,
        inicio: semana.inicio,
        fim: semana.fim,
        valores: { registros: semana.registros },
        observacao: `${semana.municipiosObservados} de ${semana.municipiosNoRecorte} municípios com observação`,
      }))}
      series={[{ chave: 'registros', nome: 'Registros observados', cor: 'var(--chart)' }]}
    />
  );
}
