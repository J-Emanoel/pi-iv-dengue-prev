import { describe, expect, it } from 'vitest';
import { gerarCsvHistorico } from '../../lib/csv';
import { formatarNumero, urlExternaSegura } from '../../lib/formatacao';
import type { RegistroSemanal } from '../../types/api';
import { agregarPorSemana, ranquearMunicipios, resumirRegistros } from './resumo';

function registro(campos: Partial<RegistroSemanal> = {}): RegistroSemanal {
  return {
    codigo_ibge: '320530',
    nome_municipio: 'Vitória',
    ano: 2026,
    semana_epidemiologica: 1,
    data_inicio: '2026-01-04',
    data_fim: '2026-01-10',
    registros_notificados: null,
    registros_por_100_mil: null,
    populacao: 1000,
    clima_presente: false,
    precipitacao_mm: null,
    temperatura_media_c: null,
    umidade_media_pct: null,
    cobertura_precipitacao_pct: null,
    cobertura_temperatura_pct: null,
    cobertura_umidade_pct: null,
    ...campos,
  };
}

describe('interpretação dos agregados no panorama', () => {
  it('mantém ausência no total, no gráfico e no ranking quando não há observações', () => {
    const dados = [registro()];
    expect(resumirRegistros(dados).total).toBeNull();
    expect(agregarPorSemana(dados)[0].registros).toBeNull();
    expect(ranquearMunicipios(dados)[0].registros).toBeNull();
    expect(formatarNumero(null)).toBe('—');
  });

  it('conta o zero explícito como observação e o distingue do município ausente', () => {
    const dados = [
      registro({ registros_notificados: 0 }),
      registro({ codigo_ibge: '320520', nome_municipio: 'Vila Velha' }),
    ];
    expect(resumirRegistros(dados)).toMatchObject({
      total: 0,
      municipiosObservados: 1,
      municipiosNoRecorte: 2,
      semanasObservadas: 1,
    });
    expect(agregarPorSemana(dados)[0]).toMatchObject({
      registros: 0,
      municipiosObservados: 1,
      municipiosNoRecorte: 2,
    });
    expect(ranquearMunicipios(dados).map((municipio) => municipio.registros)).toEqual([0, null]);
    expect(formatarNumero(0)).toBe('0');
  });

  it('ordena semanas e mantém a cobertura municipal junto de uma soma parcial', () => {
    const dados = [
      registro({ semana_epidemiologica: 2, registros_notificados: 3 }),
      registro({ registros_notificados: 7 }),
      registro({ codigo_ibge: '320520', nome_municipio: 'Vila Velha' }),
    ];
    expect(
      agregarPorSemana(dados).map((semana) => [
        semana.semana,
        semana.registros,
        semana.municipiosObservados,
        semana.municipiosNoRecorte,
      ]),
    ).toEqual([
      [1, 7, 1, 2],
      [2, 3, 1, 1],
    ]);
  });

  it('usa a última data observada, sem atribuir dados às semanas futuras do calendário', () => {
    const dados = [
      registro({ registros_notificados: 4, ano_fonte_sinan_parcial: true }),
      registro({ semana_epidemiologica: 2, data_fim: '2026-01-17' }),
    ];
    expect(resumirRegistros(dados)).toMatchObject({
      total: 4,
      ultimaData: '2026-01-10',
      semanasObservadas: 1,
      semanasNoRecorte: 2,
      fonteParcial: true,
    });
  });

  it('exporta ausências como campos vazios, preserva zero e identifica a fonte', () => {
    const csv = gerarCsvHistorico([registro(), registro({ registros_notificados: 0 })], 'sesa');
    const linhas = csv.split('\r\n');
    expect(linhas[1]).toContain('"sesa";"320530"');
    expect(linhas[1]).toContain(';"";"1000";""');
    expect(linhas[2]).toContain(';"0";"1000";""');
  });

  it('escapa aspas e neutraliza fórmulas em campos textuais exportados', () => {
    const csv = gerarCsvHistorico([registro({ nome_municipio: '=HYPERLINK("url")' })], 'sinan');
    expect(csv).toContain('"\'=HYPERLINK(""url"")"');
  });

  it('permite links HTTP de referência e rejeita esquemas executáveis', () => {
    expect(urlExternaSegura('https://exemplo.invalid/documento.pdf#page=2')).toBe(
      'https://exemplo.invalid/documento.pdf#page=2',
    );
    expect(urlExternaSegura('javascript:alert(1)')).toBeUndefined();
    expect(urlExternaSegura('data:text/html,<script>')).toBeUndefined();
  });
});
