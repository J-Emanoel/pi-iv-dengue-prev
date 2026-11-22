import { Check, Link } from 'lucide-react';
import { useEffect, useState } from 'react';

export function CopiarConsulta() {
  const [mensagem, mostrar] = useState('');
  useEffect(() => {
    if (!mensagem) return;
    const timer = setTimeout(() => mostrar(''), 4000);
    return () => clearTimeout(timer);
  }, [mensagem]);
  async function copiar() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      mostrar('Link copiado');
    } catch {
      mostrar('Copie o endereço na barra do navegador.');
    }
  }
  return (
    <div className="copy-query">
      <button className="button secondary" onClick={() => void copiar()}>
        {mensagem === 'Link copiado' ? (
          <Check size={16} aria-hidden="true" />
        ) : (
          <Link size={16} aria-hidden="true" />
        )}
        Copiar consulta
      </button>
      <span role="status">{mensagem}</span>
    </div>
  );
}
