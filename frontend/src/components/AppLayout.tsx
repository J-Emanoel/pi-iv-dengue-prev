import {
  Activity,
  ChartNoAxesCombined,
  CircleHelp,
  History,
  GitCompareArrows,
  MapPin,
  MessagesSquare,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router';

const navegacao = [
  {
    destino: '/',
    nome: 'Histórico',
    descricao: 'Consulte os registros por período',
    icone: History,
    fim: true,
  },
  {
    destino: '/comparacao',
    nome: 'Comparar',
    descricao: 'Compare duas cidades no mesmo período',
    icone: GitCompareArrows,
  },
  {
    destino: '/estimativas',
    nome: 'Previsões',
    descricao: 'Veja as estimativas disponíveis',
    icone: ChartNoAxesCombined,
  },
  {
    destino: '/assistente',
    nome: 'Assistente',
    descricao: 'Faça perguntas sobre os dados',
    icone: MessagesSquare,
  },
];

export function AppLayout({ children }: { children: ReactNode }) {
  const { pathname, search } = useLocation();
  const pagina = navegacao.find(({ destino }) => destino === pathname);

  function abrirAjuda() {
    const ajuda = document.getElementById('como-usar');
    if (ajuda instanceof HTMLDetailsElement) ajuda.open = true;
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#conteudo">
        Pular para o conteúdo
      </a>
      <aside className="sidebar" aria-label="Navegação principal">
        <NavLink to="/" className="brand" aria-label="DenguePrev, início">
          <span className="brand-symbol">
            <Activity size={27} strokeWidth={1.8} />
          </span>
          <span>
            Dengue<span className="brand-light">Prev</span>
            <small>ESPÍRITO SANTO</small>
          </span>
        </NavLink>
        <div className="nav-section-label">Explorar dados</div>
        <nav>
          {navegacao.map(({ destino, nome, descricao, icone: Icone, fim }) => (
            <NavLink
              key={destino}
              to={{ pathname: destino, search }}
              end={fim}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              <Icone size={21} aria-hidden="true" />
              <span>
                <strong>{nome}</strong>
                <small>{descricao}</small>
              </span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-note">
          <MapPin size={20} aria-hidden="true" />
          <strong>Espírito Santo</strong>
          <p>78 municípios. Registros de dengue, clima e população.</p>
        </div>
        <footer className="sidebar-footer">Projeto Integrador IV</footer>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="location-trail">
            <span>Observatório</span>
            <span aria-hidden="true">/</span>
            <strong>{pagina?.nome || 'DenguePrev'}</strong>
          </div>
          {pagina && (
            <a className="help-link" href="#como-usar" onClick={abrirAjuda}>
              <CircleHelp size={17} aria-hidden="true" />
              Como usar
            </a>
          )}
        </header>
        <main id="conteudo" className="page-content" tabIndex={-1}>
          {children}
        </main>
        <footer className="workspace-footer">
          <span>DenguePrev · Espírito Santo</span>
          <span>Consulte a origem e a data dos dados apresentados.</span>
        </footer>
      </div>
    </div>
  );
}
