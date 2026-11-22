import type { RegistroSemanal } from '../../types/api';

export interface SemanaResumida {
  semana: number;
  inicio: string;
  fim: string;
  registros: number | null;
  municipiosObservados: number;
  municipiosNoRecorte: number;
}

export interface MunicipioResumido {
  codigo: string;
  nome: string;
  registros: number | null;
  semanasObservadas: number;
  semanasNoRecorte: number;
}

export function agregarPorSemana(registros: RegistroSemanal[]): SemanaResumida[] {
  const semanas = new Map<number, SemanaResumida>();
  for (const registro of registros) {
    const semana = semanas.get(registro.semana_epidemiologica) ?? {
      semana: registro.semana_epidemiologica,
      inicio: registro.data_inicio,
      fim: registro.data_fim,
      registros: null,
      municipiosObservados: 0,
      municipiosNoRecorte: 0,
    };
    semana.municipiosNoRecorte += 1;
    if (registro.registros_notificados !== null) {
      semana.registros = (semana.registros ?? 0) + registro.registros_notificados;
      semana.municipiosObservados += 1;
    }
    semanas.set(semana.semana, semana);
  }
  return [...semanas.values()].sort((a, b) => a.semana - b.semana);
}

export function ranquearMunicipios(registros: RegistroSemanal[]): MunicipioResumido[] {
  const municipios = new Map<string, MunicipioResumido>();
  for (const registro of registros) {
    const municipio = municipios.get(registro.codigo_ibge) ?? {
      codigo: registro.codigo_ibge,
      nome: registro.nome_municipio,
      registros: null,
      semanasObservadas: 0,
      semanasNoRecorte: 0,
    };
    municipio.semanasNoRecorte += 1;
    if (registro.registros_notificados !== null) {
      municipio.registros = (municipio.registros ?? 0) + registro.registros_notificados;
      municipio.semanasObservadas += 1;
    }
    municipios.set(municipio.codigo, municipio);
  }
  return [...municipios.values()].sort((a, b) => {
    if (a.registros === null)
      return b.registros === null ? a.nome.localeCompare(b.nome, 'pt-BR') : 1;
    if (b.registros === null) return -1;
    return b.registros - a.registros || a.nome.localeCompare(b.nome, 'pt-BR');
  });
}

export function resumirRegistros(registros: RegistroSemanal[]) {
  const observados = registros.filter((registro) => registro.registros_notificados !== null);
  const municipios = ranquearMunicipios(registros);
  const semanas = agregarPorSemana(registros);
  return {
    total: observados.length
      ? observados.reduce((soma, registro) => soma + registro.registros_notificados!, 0)
      : null,
    municipiosObservados: municipios.filter((municipio) => municipio.registros !== null).length,
    municipiosNoRecorte: municipios.length,
    semanasObservadas: semanas.filter((semana) => semana.registros !== null).length,
    semanasNoRecorte: semanas.length,
    ultimaData:
      observados
        .map((registro) => registro.data_fim)
        .sort()
        .at(-1) ?? null,
    fonteParcial: registros.some(
      (registro) => registro.ano_fonte_sinan_parcial || registro.ano_fonte_sesa_parcial,
    ),
  };
}
