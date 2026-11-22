import { Database, RefreshCw, TriangleAlert } from 'lucide-react';
import type { ReactNode } from 'react';

export function EstadoConsulta({
  carregando,
  erro,
  recarregar,
  children,
}: {
  carregando: boolean;
  erro: string | null;
  recarregar: () => void;
  children: ReactNode;
}) {
  if (carregando)
    return (
      <div className="loading-state" role="status">
        <span className="spinner" />
        Consultando a fonte selecionada…
        <div className="skeleton-row">
          <i />
          <i />
          <i />
        </div>
      </div>
    );
  if (erro)
    return (
      <div className="feedback-state error-state" role="alert">
        <TriangleAlert size={28} />
        <h2>Não foi possível carregar os dados</h2>
        <p>{erro}</p>
        <button className="button secondary" onClick={recarregar}>
          <RefreshCw size={16} />
          Tentar novamente
        </button>
      </div>
    );
  return children;
}

export function SemDados({ descricao }: { descricao: string }) {
  return (
    <div className="feedback-state">
      <Database size={29} strokeWidth={1.5} />
      <h2>Nenhum dado neste recorte</h2>
      <p>{descricao}</p>
    </div>
  );
}
