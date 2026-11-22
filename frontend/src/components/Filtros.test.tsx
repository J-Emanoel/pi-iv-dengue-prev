// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it } from 'vitest';
import type { FiltrosDados } from '../types/api';
import { Filtros } from './Filtros';

function FiltrosDeTeste() {
  const [filtros, atualizar] = useState<FiltrosDados>({
    fonte: 'sinan',
    ano: 2026,
    codigoMunicipio: '',
  });
  return (
    <Filtros
      filtros={filtros}
      atualizar={atualizar}
      municipios={[{ codigo_ibge: '320530', nome: 'Vitória', populacao: null }]}
      cadastroIndisponivel={false}
    />
  );
}
afterEach(cleanup);

describe('filtros do histórico', () => {
  it('permite começar por Vitória e voltar ao estado sem perder o ano escolhido', () => {
    render(<FiltrosDeTeste />);
    fireEvent.change(screen.getByLabelText('Ano dos registros'), { target: { value: '2022' } });
    fireEvent.click(screen.getByRole('button', { name: 'Experimentar com Vitória' }));
    expect(screen.getByLabelText<HTMLSelectElement>('Município').value).toBe('320530');
    fireEvent.click(screen.getByRole('button', { name: 'Ver todos os municípios' }));
    expect(screen.getByLabelText<HTMLSelectElement>('Município').value).toBe('');
    expect(screen.getByLabelText<HTMLSelectElement>('Ano dos registros').value).toBe('2022');
  });

  it('seleciona um ano válido ao trocar para a base SESA, que tem outro período', () => {
    render(<FiltrosDeTeste />);
    fireEvent.click(screen.getByText('Alterar base'));
    fireEvent.change(screen.getByLabelText('Qual base você deseja consultar?'), {
      target: { value: 'sesa' },
    });
    const ano = screen.getByLabelText<HTMLSelectElement>('Ano dos registros');
    expect(ano.value).toBe('2024');
    expect(Array.from(ano.options, (opcao) => opcao.value)).not.toContain('2026');
    expect(screen.getByText('SESA/e-SUS VS', { selector: 'strong' })).toBeTruthy();
  });
});
