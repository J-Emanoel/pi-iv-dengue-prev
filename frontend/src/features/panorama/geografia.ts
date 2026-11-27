import malha from './municipios-es.json';

/** Projeção equiretangular local, somente para visualização da malha simplificada. */
const geometria = malha.features.map((f) => ({
  codigo: f.properties.codarea.slice(0, 6),
  poligonos: (f.geometry.type === 'Polygon'
    ? [f.geometry.coordinates]
    : f.geometry.coordinates) as number[][][][],
}));
const pontos = geometria.flatMap((m) => m.poligonos.flat(2));
const cosLatitude = Math.cos((-20 * Math.PI) / 180);
const xs = pontos.map(([x]) => x * cosLatitude);
const ys = pontos.map(([, y]) => -y);
const xMin = Math.min(...xs),
  yMin = Math.min(...ys);
const largura = Math.max(...xs) - xMin,
  altura = Math.max(...ys) - yMin;
const escala = Math.min(340 / largura, 440 / altura);
const margemX = (360 - largura * escala) / 2,
  margemY = (460 - altura * escala) / 2;
export const municipiosNoMapa = geometria.map((m) => ({
  codigo: m.codigo,
  caminho: m.poligonos
    .map((poligono) =>
      poligono
        .map(
          (anel) =>
            anel
              .map(
                ([x, y], i) =>
                  `${i ? 'L' : 'M'}${(margemX + (x * cosLatitude - xMin) * escala).toFixed(2)},${(margemY + (-y - yMin) * escala).toFixed(2)}`,
              )
              .join(' ') + ' Z',
        )
        .join(' '),
    )
    .join(' '),
}));
export const fonteMalha = malha.fonte_url;

export function corDoMapa(valor: number | null, maximo: number) {
  if (valor === null) return 'url(#sem-observacao)';
  const faixa = maximo > 0 ? Math.min(4, Math.floor((valor / maximo) * 4)) : 0;
  return `var(--map-${faixa})`;
}
