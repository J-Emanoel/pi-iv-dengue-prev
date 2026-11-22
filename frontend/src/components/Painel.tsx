import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

export function CabecalhoPagina({
  categoria,
  titulo,
  descricao,
  acao,
}: {
  categoria: string;
  titulo: string;
  descricao: string;
  acao?: ReactNode;
}) {
  return (
    <header className="page-heading">
      <div>
        <span className="eyebrow">{categoria}</span>
        <h1>{titulo}</h1>
        <p>{descricao}</p>
      </div>
      {acao}
    </header>
  );
}

export function CartaoIndicador({
  titulo,
  valor,
  detalhe,
  icone: Icone,
  destaque = false,
}: {
  titulo: string;
  valor: string;
  detalhe: string;
  icone: LucideIcon;
  destaque?: boolean;
}) {
  return (
    <article className={`stat-card ${destaque ? 'stat-featured' : ''}`}>
      <div className="stat-heading">
        <span>{titulo}</span>
        <span className="stat-icon">
          <Icone size={19} strokeWidth={1.8} aria-hidden="true" />
        </span>
      </div>
      <strong className="stat-value">{valor}</strong>
      <span className="stat-detail">{detalhe}</span>
    </article>
  );
}

export function Painel({
  titulo,
  descricao,
  complemento,
  children,
  className = '',
}: {
  titulo: string;
  descricao?: string;
  complemento?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <div>
          <h2>{titulo}</h2>
          {descricao && <p>{descricao}</p>}
        </div>
        {complemento}
      </div>
      {children}
    </section>
  );
}
