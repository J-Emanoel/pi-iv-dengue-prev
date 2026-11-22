import type { Comparacao, Fonte, RegistroSemanal } from '../types/api';

function celulaCsv(valor: unknown): string {
  let texto = valor == null ? '' : String(valor);
  if (typeof valor === 'string' && /^[\s]*[=+\-@]/.test(texto)) texto = `'${texto}`;
  return `"${texto.replaceAll('"', '""')}"`;
}

export function gerarCsvHistorico(registros: RegistroSemanal[], fonte: Fonte): string {
  const cabecalho = [
    'fonte',
    'codigo_municipio',
    'municipio',
    'ano_epidemiologico',
    'semana',
    'data_inicio',
    'data_fim',
    'registros',
    'populacao',
    'registros_por_100_mil',
    'estacao',
    'chuva_mm',
    'temperatura_media_c',
    'umidade_media_pct',
    'cobertura_chuva_pct',
    'cobertura_temperatura_pct',
    'cobertura_umidade_pct',
  ];
  const linhas = registros.map((registro) => [
    fonte,
    registro.codigo_ibge,
    registro.nome_municipio,
    registro.ano,
    registro.semana_epidemiologica,
    registro.data_inicio,
    registro.data_fim,
    registro.registros_notificados,
    registro.populacao,
    registro.registros_por_100_mil,
    registro.nome_estacao,
    registro.precipitacao_mm,
    registro.temperatura_media_c,
    registro.umidade_media_pct,
    registro.cobertura_precipitacao_pct,
    registro.cobertura_temperatura_pct,
    registro.cobertura_umidade_pct,
  ]);
  return [cabecalho, ...linhas].map((linha) => linha.map(celulaCsv).join(';')).join('\r\n');
}

export function baixarCsv(conteudo: string, nome: string): void {
  const url = URL.createObjectURL(
    new Blob(['\uFEFF', conteudo], { type: 'text/csv;charset=utf-8' }),
  );
  const link = document.createElement('a');
  link.href = url;
  link.download = nome;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function gerarCsvComparacao(comparacao: Comparacao): string {
  const comuns = new Set(comparacao.semanas_observadas_em_comum);
  const linhas = comparacao.municipios.flatMap((m) =>
    m.semanas.map((s) => [
      comparacao.fonte,
      comparacao.ano,
      m.codigo_ibge,
      m.nome_municipio,
      s.semana_epidemiologica,
      s.data_inicio,
      s.data_fim,
      s.registros_notificados,
      s.registros_por_100_mil,
      comuns.has(s.semana_epidemiologica),
    ]),
  );
  return [
    [
      'fonte',
      'ano_epidemiologico',
      'codigo_municipio',
      'municipio',
      'semana',
      'data_inicio',
      'data_fim',
      'registros',
      'registros_por_100_mil',
      'semana_observada_em_comum',
    ],
    ...linhas,
  ]
    .map((linha) => linha.map(celulaCsv).join(';'))
    .join('\r\n');
}
