import { useState } from 'react';
import { Download, ArrowLeftRight } from 'lucide-react';
import { GraficoTemporal } from '../../components/GraficoTemporal';
import { AjudaPagina } from '../../components/AjudaPagina';
import { CopiarConsulta } from '../../components/CopiarConsulta';
import { EstadoConsulta } from '../../components/EstadoConsulta';
import { Filtros, SeletorMunicipio } from '../../components/Filtros';
import type { PropriedadesFiltros } from '../../components/Filtros';
import { CabecalhoPagina, Painel } from '../../components/Painel';
import { useApi } from '../../hooks/useApi';
import { caminhoComparacao } from '../../services/api';
import { baixarCsv, gerarCsvComparacao } from '../../lib/csv';
import { FONTES, formatarData, formatarNumero } from '../../lib/formatacao';
import type { Comparacao } from '../../types/api';

export default function ComparacaoPage(props: PropriedadesFiltros) {
  const { filtros, atualizar } = props;
  const primeiro = filtros.codigoMunicipio || '320530';
  const segundo = filtros.compararCom || (primeiro === '320520' ? '320530' : '320520');
  const distintos = primeiro !== segundo;
  const consulta = useApi<Comparacao>(
    distintos ? caminhoComparacao(filtros, primeiro, segundo) : null,
  );
  const dados = consulta.dados;
  const [medida, mudarMedida] = useState<'registros_notificados' | 'registros_por_100_mil'>(
    'registros_notificados',
  );
  const comuns = new Set(dados?.semanas_observadas_em_comum);
  const porSemana = new Map(dados?.municipios[1]?.semanas.map((s) => [s.semana_epidemiologica, s]));
  const serie =
    dados?.municipios[0]?.semanas.map((s) => ({
      semana: s.semana_epidemiologica,
      inicio: s.data_inicio,
      fim: s.data_fim,
      valores: {
        a: comuns.has(s.semana_epidemiologica) ? s[medida] : null,
        b: comuns.has(s.semana_epidemiologica)
          ? (porSemana.get(s.semana_epidemiologica)?.[medida] ?? null)
          : null,
      },
    })) ?? [];
  return (
    <>
      <CabecalhoPagina
        categoria="COMPARAÇÃO MUNICIPAL"
        titulo="Duas cidades, o mesmo período"
        descricao="Compare registros usando a mesma fonte e somente semanas observadas nas duas cidades."
        acao={<CopiarConsulta />}
      />
      <Filtros {...props} modo="comparacao" />
      <section className="comparison-picker panel" aria-label="Municípios para comparar">
        <SeletorMunicipio
          id="cidade-a"
          rotulo="Primeiro município"
          valor={primeiro}
          municipios={props.municipios}
          selecionar={(codigo) => atualizar({ ...filtros, codigoMunicipio: codigo })}
          cadastroIndisponivel={props.cadastroIndisponivel}
        />
        <button
          className="button secondary swap-cities"
          onClick={() => atualizar({ ...filtros, codigoMunicipio: segundo, compararCom: primeiro })}
        >
          <ArrowLeftRight size={18} aria-hidden="true" />
          Inverter cidades
        </button>
        <SeletorMunicipio
          id="cidade-b"
          rotulo="Segundo município"
          valor={segundo}
          municipios={props.municipios}
          selecionar={(codigo) => atualizar({ ...filtros, compararCom: codigo })}
          cadastroIndisponivel={props.cadastroIndisponivel}
        />
      </section>
      {!distintos && (
        <p className="inline-error" role="alert">
          Escolha dois municípios diferentes para comparar.
        </p>
      )}
      {distintos && (
        <EstadoConsulta {...consulta}>
          {dados && (
            <>
              <div className="context-strip">
                <span>
                  {FONTES[filtros.fonte].nome} · {formatarData(dados.periodo.inicio)} a{' '}
                  {formatarData(dados.periodo.fim)}
                </span>
                <span>{comuns.size} semanas observadas em comum</span>
              </div>
              <div className="comparison-results">
                {dados.municipios.map((m, i) => (
                  <article key={m.codigo_ibge} className={`comparison-result city-${i}`}>
                    <span>{i === 0 ? 'Primeiro município' : 'Segundo município'}</span>
                    <h2>{m.nome_municipio}</h2>
                    <strong>{formatarNumero(m.registros_nas_semanas_comuns)}</strong>
                    <p>registros nas {comuns.size} semanas comuns</p>
                    <small>
                      {m.resumo_intervalo.semanas_com_registro} de{' '}
                      {m.resumo_intervalo.semanas_consultadas} semanas têm observação nesta cidade.
                    </small>
                  </article>
                ))}
              </div>
              <div className="data-note">
                <p>
                  {comuns.size ? (
                    <>
                      Diferença de {dados.municipios[1]?.nome_municipio} em relação a{' '}
                      {dados.municipios[0]?.nome_municipio}:{' '}
                      <strong className="inline-value">
                        {formatarNumero(dados.municipios[1]?.diferenca_para_primeiro_municipio)}
                      </strong>{' '}
                      registros. Contagens absolutas não ajustam diferenças populacionais.
                    </>
                  ) : (
                    'Não há semanas observadas em comum no intervalo. A comparação permanece indisponível; ausência não foi transformada em zero.'
                  )}
                </p>
              </div>
              <Painel
                titulo="Histórico nas semanas comuns"
                descricao="Lacunas marcam as semanas excluídas da comparação. A opção por 100 mil usa o denominador anual de cada município."
                complemento={
                  <button
                    className="button secondary"
                    onClick={() =>
                      baixarCsv(
                        gerarCsvComparacao(dados),
                        `dengueprev-comparacao-${filtros.fonte}-${filtros.ano}.csv`,
                      )
                    }
                  >
                    <Download size={16} aria-hidden="true" />
                    Baixar comparação (CSV)
                  </button>
                }
              >
                <div className="segmented-control" role="group" aria-label="Medida da comparação">
                  <button
                    aria-pressed={medida === 'registros_notificados'}
                    onClick={() => mudarMedida('registros_notificados')}
                  >
                    Registros
                  </button>
                  <button
                    aria-pressed={medida === 'registros_por_100_mil'}
                    onClick={() => mudarMedida('registros_por_100_mil')}
                  >
                    Por 100 mil habitantes
                  </button>
                </div>
                <GraficoTemporal
                  rotulo="Gráfico comparativo municipal"
                  pontos={serie}
                  casasDecimais={medida === 'registros_por_100_mil' ? 2 : 0}
                  series={[
                    {
                      chave: 'a',
                      nome: dados.municipios[0]?.nome_municipio ?? 'Primeiro município',
                      cor: 'var(--chart)',
                    },
                    {
                      chave: 'b',
                      nome: dados.municipios[1]?.nome_municipio ?? 'Segundo município',
                      cor: 'var(--violet)',
                      tracejada: true,
                    },
                  ]}
                />
                <details className="consultation-details">
                  <summary>Ver valores semanais em tabela</summary>
                  <div className="table-scroll">
                    <table>
                      <caption>
                        {medida === 'registros_por_100_mil'
                          ? 'Registros por 100 mil habitantes'
                          : 'Registros'}{' '}
                        · somente semanas comuns
                      </caption>
                      <thead>
                        <tr>
                          <th>Semana</th>
                          <th>{dados.municipios[0]?.nome_municipio}</th>
                          <th>{dados.municipios[1]?.nome_municipio}</th>
                          <th>Comparável?</th>
                        </tr>
                      </thead>
                      <tbody>
                        {serie.map((s) => (
                          <tr key={s.semana}>
                            <td>{s.semana}</td>
                            <td>{formatarNumero(s.valores.a, 2)}</td>
                            <td>{formatarNumero(s.valores.b, 2)}</td>
                            <td>{comuns.has(s.semana) ? 'Sim' : 'Sem observação em comum'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              </Painel>
              <p className="data-legend">
                {dados.limitacoes.join(' ')} A taxa descritiva não equivale a incidência de casos
                confirmados.
              </p>
            </>
          )}
        </EstadoConsulta>
      )}
      <AjudaPagina
        passos={[
          'Escolha a fonte, o ano e o intervalo de semanas.',
          'Selecione duas cidades. Inverta a ordem para trocar a referência da diferença.',
          'Confira as semanas comuns, alterne entre contagens e valores por 100 mil e baixe a comparação ou copie o link.',
        ]}
      />
    </>
  );
}
