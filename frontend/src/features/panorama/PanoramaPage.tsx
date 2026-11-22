import { Activity, CalendarDays, Download, Info, MapPin, Rows3 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { AjudaPagina } from '../../components/AjudaPagina';
import { CopiarConsulta } from '../../components/CopiarConsulta';
import { EstadoConsulta, SemDados } from '../../components/EstadoConsulta';
import { Filtros } from '../../components/Filtros';
import type { PropriedadesFiltros } from '../../components/Filtros';
import { CabecalhoPagina, CartaoIndicador, Painel } from '../../components/Painel';
import { useApi } from '../../hooks/useApi';
import { baixarCsv, gerarCsvHistorico } from '../../lib/csv';
import { intervaloSemanal } from '../../lib/filtros';
import { FONTES, formatarData, formatarNumero } from '../../lib/formatacao';
import { caminhoHistorico } from '../../services/api';
import type { RegistroSemanal } from '../../types/api';
import { GraficoSemanal } from './GraficoSemanal';
import { IndicadoresContexto } from './IndicadoresContexto';
import { MapaMunicipios } from './MapaMunicipios';
import { RankingMunicipios } from './RankingMunicipios';
import { agregarPorSemana, ranquearMunicipios, resumirRegistros } from './resumo';
import { indicadoresPorMunicipio, selecionarPeriodo } from './analise';

const VISOES = {
  historico: 'Histórico',
  mapa: 'Mapa municipal',
  contexto: 'População e clima',
} as const;
type Visao = keyof typeof VISOES;

export default function PanoramaPage(props: PropriedadesFiltros) {
  const { filtros, atualizar } = props;
  // Uma grade anual estadual alimenta o mapa, o ranking e a cidade selecionada.
  // Trocar município ou semana não repete a leitura ao banco.
  const consulta = useApi<RegistroSemanal[]>(caminhoHistorico({ ...filtros, codigoMunicipio: '' }));
  const [visao, escolherVisao] = useState<Visao>('historico');
  const { inicio, fim, maximo } = intervaloSemanal(filtros);
  const periodoEstadual = useMemo(
    () => selecionarPeriodo(consulta.dados ?? [], filtros),
    [consulta.dados, inicio, fim],
  );
  const registros = useMemo(
    () =>
      filtros.codigoMunicipio
        ? periodoEstadual.filter((r) => r.codigo_ibge === filtros.codigoMunicipio)
        : periodoEstadual,
    [periodoEstadual, filtros.codigoMunicipio],
  );
  const semanas = useMemo(() => agregarPorSemana(registros), [registros]);
  const municipios = useMemo(() => ranquearMunicipios(registros), [registros]);
  const resumo = useMemo(() => resumirRegistros(registros), [registros]);
  const indicadores = useMemo(() => indicadoresPorMunicipio(periodoEstadual), [periodoEstadual]);
  const fonte = FONTES[filtros.fonte];
  const local =
    props.municipios.find((m) => m.codigo_ibge === filtros.codigoMunicipio)?.nome ||
    (filtros.codigoMunicipio ? 'Município selecionado' : 'Espírito Santo');
  const ultimaObservada = Math.max(
    0,
    ...(consulta.dados ?? [])
      .filter(
        (r) =>
          (!filtros.codigoMunicipio || r.codigo_ibge === filtros.codigoMunicipio) &&
          r.registros_notificados !== null,
      )
      .map((r) => r.semana_epidemiologica),
  );
  function selecionarMunicipio(codigo: string) {
    atualizar({ ...filtros, codigoMunicipio: codigo });
  }
  function exportar() {
    if (registros.length)
      baixarCsv(
        gerarCsvHistorico(registros, filtros.fonte),
        `dengueprev-${filtros.fonte}-${filtros.ano}-${filtros.codigoMunicipio || 'es'}-semanas-${inicio}-${fim}.csv`,
      );
  }

  return (
    <>
      <CabecalhoPagina
        categoria="DADOS OBSERVADOS"
        titulo="Explore o histórico de dengue"
        descricao="Consulte o histórico, selecione cidades no mapa e explore os indicadores do período."
        acao={
          <div className="heading-actions">
            <CopiarConsulta />
            <button
              className="button secondary"
              onClick={exportar}
              disabled={!registros.length || consulta.carregando}
            >
              <Download size={16} aria-hidden="true" />
              Baixar dados (CSV)
            </button>
          </div>
        }
      />
      <Filtros {...props} />
      <div className="exploration-toolbar">
        <div className="dashboard-tabs" role="group" aria-label="Visualização do dashboard">
          {(Object.keys(VISOES) as Visao[]).map((v) => (
            <button key={v} aria-pressed={visao === v} onClick={() => escolherVisao(v)}>
              {VISOES[v]}
            </button>
          ))}
        </div>
        <div className="period-shortcuts" role="group" aria-label="Atalhos de período">
          <button
            className="text-button"
            disabled={!ultimaObservada || consulta.carregando}
            onClick={() =>
              atualizar({
                ...filtros,
                semanaInicial: Math.max(1, ultimaObservada - 7),
                semanaFinal: ultimaObservada,
              })
            }
          >
            8 semanas até o último registro
          </button>
          <button
            className="text-button"
            disabled={inicio === 1 && fim === maximo}
            onClick={() =>
              atualizar({ ...filtros, semanaInicial: undefined, semanaFinal: undefined })
            }
          >
            Ano inteiro
          </button>
        </div>
      </div>
      <EstadoConsulta {...consulta}>
        {registros.length ? (
          <>
            <div className="context-strip">
              <span>
                {local} / {filtros.ano} · semanas {inicio}–{fim}
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
                detalhe="Soma dos registros disponíveis na seleção"
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
            {visao === 'historico' && (
              <div className={`dashboard-grid ${filtros.codigoMunicipio ? 'single-region' : ''}`}>
                <Painel
                  titulo={`Registros por semana · ${local}`}
                  descricao="Passe sobre o gráfico ou abra a tabela para consultar os valores e as datas."
                  complemento={
                    <span className="chart-legend">
                      <i />
                      {fonte.nome}
                    </span>
                  }
                >
                  <GraficoSemanal semanas={semanas} />
                  <p className="panel-footnote">
                    <Info size={14} aria-hidden="true" />
                    Semanas sem observação aparecem como lacunas. Na consulta estadual, o número de
                    municípios com dados pode variar entre as semanas.
                  </p>
                </Painel>
                {!filtros.codigoMunicipio && (
                  <Painel
                    titulo="Ranking de registros"
                    descricao="Busque uma cidade e clique no nome para consultar seu histórico."
                  >
                    <RankingMunicipios municipios={municipios} selecionar={selecionarMunicipio} />
                    <p className="panel-footnote">
                      Contagens sem ajuste populacional; este ranking não representa risco
                      epidemiológico.
                    </p>
                  </Painel>
                )}
              </div>
            )}
            {visao === 'mapa' && (
              <MapaMunicipios
                indicadores={indicadores}
                selecionado={filtros.codigoMunicipio}
                selecionar={selecionarMunicipio}
              />
            )}
            {visao === 'contexto' && (
              <IndicadoresContexto
                registros={registros}
                municipioSelecionado={Boolean(filtros.codigoMunicipio)}
                selecionarExemplo={() => selecionarMunicipio('320530')}
              />
            )}
            <div className="data-note">
              <span className="note-icon">
                <Info size={20} aria-hidden="true" />
              </span>
              <div>
                <strong>O que esses registros representam?</strong>
                <p>
                  São contagens da base {fonte.nome}, agrupadas por {fonte.referencia.toLowerCase()}
                  . Incluem as classificações presentes na extração e não equivalem automaticamente
                  a casos confirmados. Cada visualização respeita o intervalo escolhido.
                </p>
              </div>
            </div>
            <details className="data-details">
              <summary>Ver os registros em tabela</summary>
              <div className="table-scroll">
                <table>
                  <caption>
                    Observações semanais · {fonte.nome} · {local} · {filtros.ano}
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
                    {semanas.map((s) => (
                      <tr key={s.semana}>
                        <td>Semana {s.semana}</td>
                        <td>
                          {formatarData(s.inicio)}–{formatarData(s.fim)}
                        </td>
                        <td className="numeric">{formatarNumero(s.registros)}</td>
                        <td className="numeric">
                          {s.municipiosObservados} de {s.municipiosNoRecorte}
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
          <SemDados descricao="Selecione outra fonte, período ou município para consultar o histórico disponível." />
        )}
      </EstadoConsulta>
      <AjudaPagina
        passos={[
          'Escolha a fonte, o ano e o intervalo de semanas. Os resultados se atualizam automaticamente.',
          'Use Histórico, Mapa municipal ou População e clima. Clique em uma cidade no ranking ou no mapa para selecioná-la.',
          'Os atalhos selecionam o ano inteiro ou o intervalo de oito semanas até a última observação; lacunas continuam identificadas. Use Comparar no menu para colocar duas cidades lado a lado.',
          'Baixe o CSV com os dados filtrados ou copie a consulta para compartilhar o mesmo endereço e os mesmos filtros.',
        ]}
      />
    </>
  );
}
