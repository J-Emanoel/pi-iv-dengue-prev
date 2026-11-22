import { ChevronDown, CircleHelp } from 'lucide-react';

/** Ajuda curta, acessível por teclado e disponível sem interromper a consulta. */
export function AjudaPagina({ passos }: { passos: string[] }) {
  return (
    <details className="page-help" id="como-usar">
      <summary>
        <CircleHelp size={19} aria-hidden="true" />
        <span>Como usar esta página</span>
        <ChevronDown className="help-chevron" size={17} aria-hidden="true" />
      </summary>
      <ol>
        {passos.map((passo) => (
          <li key={passo}>{passo}</li>
        ))}
      </ol>
    </details>
  );
}
