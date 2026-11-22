import { Activity, CalendarDays, Download, Info, MapPin, Rows3 } from 'lucide-react';
import { useMemo } from 'react';
import { AjudaPagina } from '../../components/AjudaPagina';
import { EstadoConsulta, SemDados } from '../../components/EstadoConsulta';
import { Filtros } from '../../components/Filtros';
import type { PropriedadesFiltros } from '../../components/Filtros';
import { CabecalhoPagina, CartaoIndicador, Painel } from '../../components/Painel';
import { useApi } from '../../hooks/useApi';
import { baixarCsv, gerarCsvHistorico } from '../../lib/csv';
import { FONTES, formatarData, formatarNumero } from '../../lib/formatacao';
import { caminhoHistorico } from '../../services/api';
import type { RegistroSemanal } from '../../types/api';
import { GraficoSemanal } from './GraficoSemanal';
import { RankingMunicipios } from './RankingMunicipios';
import { agregarPorSemana, ranquearMunicipios, resumirRegistros } from './resumo';

export default function PanoramaPage(props: PropriedadesFiltros) {
  const { filtros } = props;
  const consulta = useApi<RegistroSemanal[]>(caminhoHistorico(filtros));
  const registros = consulta.dados;
  const semanas = useMemo(() => agregarPorSemana(registros ?? []), [registros]);
  const municipios = useMemo(() => ranquearMunicipios(registros ?? []), [registros]);
  const resumo = useMemo(() => resumirRegistros(registros ?? []), [registros]);
  const fonte = FONTES[filtros.fonte];
  const local =
    props.municipios.find((municipio) => municipio.codigo_ibge === filtros.codigoMunicipio)?.nome ||
    'Espírito Santo';

  function exportar() {
    if (registros)
      baixarCsv(
        gerarCsvHistorico(registros, filtros.fonte),
        `dengueprev-${filtros.fonte}-${filtros.ano}.csv`,
      );
  }

  return (
    <>
      <CabecalhoPagina
        categoria="DADOS OBSERVADOS"
        titulo="Histórico de dengue"
        descricao="Consulte os registros de um período e veja como eles se distribuem por semana e município."
        acao={
          <button
            className="button secondary"
            onClick={exportar}
            disabled={!registros?.length || consulta.carregando}
          >
            <Download size={16} />
            Baixar dados (CSV)
          </button>
        }
      />
      <Filtros {...props} />
      <EstadoConsulta {...consulta}>
        {registros?.length ? (
          <>
            <div className="context-strip">
              <span>
                {local} <span className="context-separator">/</span> {filtros.ano}
              </span>
              <span>
                {fonte.nome} · {fonte.referencia}
                {resumo.fonteParcial && <span className="badge amber">Ano com dados parciais</span>}
              </span>
            </div>
            <div className="stats-grid">
              <CartaoIndicador
                titulo="Registros no período"
                valor={formatarNumero(resumo.total)}
                detalhe="Soma dos registros disponíveis na base"
                icone={Activity}
                destaque
              />
              <CartaoIndicador
                titulo="Municípios com dados"
                valor={`${resumo.municipiosObservados} de ${resumo.municipiosNoRecorte}`}
                detalhe="Municípios com ao menos uma observação"
                icone={MapPin}
              />
              <CartaoIndicador
                titulo="Semanas com dados"
                valor={`${resumo.semanasObservadas} de ${resumo.semanasNoRecorte}`}
                detalhe="Semanas com registros informados"
                icone={Rows3}
              />
              <CartaoIndicador
                titulo="Última semana com registro"
                valor={formatarData(resumo.ultimaData)}
                detalhe="Data final dessa semana, na seleção atual"
                icone={CalendarDays}
              />
            </div>
            <div className={`dashboard-grid ${filtros.codigoMunicipio ? 'single-region' : ''}`}>
              <Painel
                titulo={`Registros por semana · ${local}`}
                descricao="Passe o mouse sobre o gráfico para ver os valores e as datas."
                complemento={
                  <span className="chart-legend">
                    <i />
                    {fonte.nome}
                  </span>
                }
                className="history-panel"
              >
                <GraficoSemanal semanas={semanas} />
                <p className="panel-footnote">
                  <Info size={14} />
                  Semanas sem observação aparecem como lacunas. Na consulta estadual, o número de
                  municípios com dados pode variar entre as semanas.
                </p>
              </Painel>
              {!filtros.codigoMunicipio && (
                <Painel
                  titulo="Ranking de registros"
                  descricao="Municípios com as maiores contagens no período."
                  className="ranking-panel"
                >
                  <RankingMunicipios municipios={municipios} />
                  <p className="panel-footnote">
                    Contagens sem ajuste populacional; este ranking não representa risco
                    epidemiológico.
                  </p>
                </Painel>
              )}
            </div>
            <div className="data-note">
              <span className="note-icon">
                <Info size={20} />
              </span>
              <div>
                <strong>O que esses registros representam?</strong>
                <p>
                  São contagens da base {fonte.nome}, agrupadas por {fonte.referencia.toLowerCase()}
                  . Incluem as classificações presentes na extração e não equivalem automaticamente
                  a casos confirmados.
                </p>
              </div>
            </div>
            <details className="data-details">
              <summary>Ver os registros em tabela</summary>
              <div className="table-scroll">
                <table>
                  <caption>
                    Observações semanais · {fonte.nome} · {filtros.ano}
                  </caption>
                  <thead>
                    <tr>
                      <th>Semana</th>
                      <th>Período</th>
                      <th className="numeric">Registros</th>
                      <th className="numeric">Municípios com dados</th>
                    </tr>
                  </thead>
                  <tbody>
                    {semanas.map((semana) => (
                      <tr key={semana.semana}>
                        <td>Semana {semana.semana}</td>
                        <td>
                          {formatarData(semana.inicio)}–{formatarData(semana.fim)}
                        </td>
                        <td className="numeric">{formatarNumero(semana.registros)}</td>
                        <td className="numeric">
                          {semana.municipiosObservados} de {semana.municipiosNoRecorte}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
            <p className="data-legend">
              <strong>Como ler valores ausentes:</strong> “—” indica valor não disponível na base.
              “0” é uma contagem informada igual a zero.
            </p>
          </>
        ) : (
          <SemDados descricao="Selecione outra fonte, ano ou município para consultar o histórico disponível." />
        )}
      </EstadoConsulta>
      <AjudaPagina
        passos={[
          'Escolha um município e um ano. Para começar com um exemplo real, clique em Experimentar com Vitória.',
          'Leia o total de registros e passe o mouse sobre o gráfico para consultar cada semana.',
          'Selecione todos os municípios para ver o ranking estadual. Você também pode abrir a tabela ou baixar os dados filtrados.',
        ]}
      />
    </>
  );
}
