import { Moon, Sun } from 'lucide-react';
import { useTema } from '../hooks/useTema';

export function AlternarTema() {
  const { tema, alternar } = useTema();
  const escuro = tema === 'dark';
  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={alternar}
      aria-pressed={escuro}
      aria-label={escuro ? 'Usar tema claro' : 'Usar tema escuro'}
      title={escuro ? 'Tema claro' : 'Tema escuro'}
    >
      {escuro ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
    </button>
  );
}
