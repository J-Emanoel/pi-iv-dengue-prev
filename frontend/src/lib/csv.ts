import type { Fonte, RegistroSemanal } from '../types/api';

function celulaCsv(valor: unknown): string {
  let texto = valor == null ? '' : String(valor);
  if (/^[\s]*[=+\-@]/.test(texto)) texto = `'${texto}`;
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
