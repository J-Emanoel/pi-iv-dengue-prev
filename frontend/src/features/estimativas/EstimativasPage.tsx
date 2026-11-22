import { Activity, CalendarDays, CircleHelp, Layers, MapPin } from 'lucide-react';
import { AjudaPagina } from '../../components/AjudaPagina';
import { EstadoConsulta, SemDados } from '../../components/EstadoConsulta';
import { Filtros } from '../../components/Filtros';
import type { PropriedadesFiltros } from '../../components/Filtros';
import { CabecalhoPagina, CartaoIndicador, Painel } from '../../components/Painel';
import { useApi } from '../../hooks/useApi';
import { FONTES, formatarData, formatarNumero } from '../../lib/formatacao';
import { caminhoPrevisoes } from '../../services/api';
import type { Previsoes } from '../../types/api';

const MOTIVOS = {
  historico_incompleto: 'Histórico incompleto',
  clima_insuficiente: 'Clima insuficiente',
};

export default function EstimativasPage(props: PropriedadesFiltros) {
  const { fonte, codigoMunicipio } = props.filtros;
  const consulta = useApi<Previsoes>(caminhoPrevisoes(fonte, codigoMunicipio));
  const previsoes = consulta.dados;
  const modelo = previsoes?.modelo;
  const selecionado = codigoMunicipio
    ? previsoes?.resultados.find((resultado) => resultado.codigo_ibge === codigoMunicipio)
    : undefined;

  return (
    <>
      <CabecalhoPagina
        categoria="ESTIMATIVAS DO MODELO"
        titulo="Previsões disponíveis"
        descricao="Veja a estimativa para a semana seguinte aos dados da base. Confira o período antes de interpretar o resultado."
      />
      <Filtros {...props} modo="previsao" />
      <EstadoConsulta {...consulta}>
        {previsoes && modelo ? (
          <>
            <div className="context-strip">
              <span>Base {FONTES[fonte].nome} · estimativa a partir do histórico disponível</span>
              <span className="badge amber">Confira a data da previsão</span>
            </div>
            <div className="stats-grid">
              <CartaoIndicador
                titulo="Semana da previsão"
                valor={`${formatarData(previsoes.data_inicio, true)}–${formatarData(previsoes.data_fim, true)}`}
                detalhe={`Semana ${previsoes.semana_epidemiologica} do ano epidemiológico ${previsoes.ano}`}
                icone={CalendarDays}
                destaque
              />
              <CartaoIndicador
                titulo="Últimos dados da base"
                valor={formatarData(modelo.fim_historico)}
                detalhe="A previsão parte do histórico até esta data"
                icone={Layers}
              />
              <CartaoIndicador
                titulo="Municípios com previsão"
                valor={`${previsoes.municipios_com_previsao} de ${previsoes.total_municipios}`}
                detalhe="Há histórico e clima suficientes para estimar"
                icone={MapPin}
              />
              <CartaoIndicador
                titulo="Método utilizado"
                valor={modelo.familia === 'persistencia' ? 'Última contagem' : modelo.modelo}
                detalhe="Entenda o cálculo na explicação abaixo"
                icone={Activity}
              />
            </div>
            {selecionado && (
              <section
                className={`prediction-result ${selecionado.status === 'disponivel' ? '' : 'prediction-unavailable'}`}
                aria-label={`Previsão para ${selecionado.nome_municipio}`}
              >
                <div>
                  <span className="eyebrow">RESULTADO DO MUNICÍPIO</span>
                  <h2>{selecionado.nome_municipio}</h2>
                  <p>
                    Período: {formatarData(previsoes.data_inicio)} a{' '}
                    {formatarData(previsoes.data_fim)}
                  </p>
                </div>
                <div className="prediction-value">
                  {selecionado.registros_previstos !== null ? (
                    <>
                      <strong>{formatarNumero(selecionado.registros_previstos, 2)}</strong>
                      <span>registros estimados</span>
                    </>
                  ) : (
                    <>
                      <strong>Previsão indisponível</strong>
                      <span>
                        {selecionado.motivos.map((motivo) => MOTIVOS[motivo]).join(' · ')}
                      </span>
                    </>
                  )}
                </div>
                <p className="prediction-baseline">
                  Última contagem observada:{' '}
                  {selecionado.registros_ultima_semana !== null ? (
                    <>
                      <strong>{formatarNumero(selecionado.registros_ultima_semana)}</strong>{' '}
                      registros.
                    </>
                  ) : (
                    'não disponível.'
                  )}{' '}
                  A previsão não corresponde a uma confirmação de novos casos.
                </p>
              </section>
            )}
            <div className="data-note">
              <span className="note-icon">
                <CircleHelp size={21} />
              </span>
              <div>
                <strong>
                  {modelo.familia === 'persistencia'
                    ? 'Como esta previsão é calculada?'
                    : 'O que significa esta estimativa?'}
                </strong>
                <p>
                  {modelo.familia === 'persistencia'
                    ? 'O método selecionado repete a última contagem observada. Por isso, o valor estimado pode ser igual ao da última semana. Ele não demonstrou ganho na antecipação de crescimento.'
                    : modelo.descricao_metodo}{' '}
                  O período apresentado depende da base disponível e não corresponde automaticamente
                  à semana atual.
                </p>
              </div>
            </div>
            <Painel
              titulo="Previsões por município"
              descricao="Compare a última contagem observada com o valor estimado para o período informado."
              complemento={<span className="badge">{FONTES[fonte].nome}</span>}
            >
              {previsoes.resultados.length ? (
                <div className="table-scroll">
                  <table>
                    <caption className="sr-only">
                      Estimativas por município da fonte {FONTES[fonte].nome}
                    </caption>
                    <thead>
                      <tr>
                        <th>Município</th>
                        <th className="numeric">Última contagem observada</th>
                        <th className="numeric">Registros estimados</th>
                        <th>Situação da previsão</th>
                      </tr>
                    </thead>
                    <tbody>
                      {previsoes.resultados.map((resultado) => (
                        <tr key={resultado.codigo_ibge}>
                          <td>
                            <strong>{resultado.nome_municipio}</strong>
                            <small className="table-subtitle">{resultado.codigo_ibge}</small>
                          </td>
                          <td className="numeric">
                            {formatarNumero(resultado.registros_ultima_semana)}
                          </td>
                          <td className="numeric estimate-number">
                            {formatarNumero(resultado.registros_previstos, 2)}
                          </td>
                          <td>
                            <span
                              className={`badge ${resultado.status === 'disponivel' ? 'green' : 'neutral'}`}
                            >
                              {resultado.status === 'disponivel'
                                ? 'Previsão disponível'
                                : 'Ainda faltam dados'}
                            </span>
                            {resultado.motivos.length > 0 && (
                              <small className="table-subtitle">
                                {resultado.motivos.map((motivo) => MOTIVOS[motivo]).join(' · ')}
                              </small>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <SemDados descricao="Nenhum município foi retornado pelo experimento selecionado." />
              )}
            </Painel>
            <details className="data-details">
              <summary>Entender o método, a avaliação e as limitações</summary>
              <div className="method-details">
                <p>
                  <strong>Estratégia:</strong> {modelo.modelo} · {modelo.descricao_metodo}
                </p>
                <p>
                  <strong>Avaliação em {modelo.ano_teste}:</strong> diferença absoluta média de{' '}
                  {formatarNumero(modelo.teste?.mae, 2)} registros entre o estimado e o observado no
                  teste (MAE). Esse erro não é uma margem garantida para cada previsão.
                </p>
                <p>
                  <strong>Identificação da versão:</strong> <code>{modelo.versao}</code>. Base do
                  experimento: <code>{modelo.dataset_id}</code>.
                </p>
                <p>
                  <strong>Período histórico:</strong> {formatarData(modelo.inicio_historico)} a{' '}
                  {formatarData(modelo.fim_historico)}.
                </p>
                <ul>
                  {modelo.limitacoes.map((limitacao) => (
                    <li key={limitacao}>{limitacao}</li>
                  ))}
                </ul>
              </div>
            </details>
          </>
        ) : null}
      </EstadoConsulta>
      <AjudaPagina
        passos={[
          'Escolha um município para ver sua estimativa ou mantenha todos para consultar a tabela estadual.',
          'Confira a semana da previsão e a data dos últimos dados utilizados. O período pode ser anterior à semana atual.',
          'Leia o valor estimado e a última contagem observada. Quando faltarem dados, a página explica por que a previsão está indisponível.',
        ]}
      />
    </>
  );
}
