import { lazy, Suspense, useState } from 'react';
import { NavLink, Route, Routes } from 'react-router';
import { AppLayout } from './components/AppLayout';
import { useApi } from './hooks/useApi';
import type { FiltrosDados, Municipio } from './types/api';

const PanoramaPage = lazy(() => import('./features/panorama/PanoramaPage'));
const EstimativasPage = lazy(() => import('./features/estimativas/EstimativasPage'));
const AssistentePage = lazy(() => import('./features/assistente/AssistentePage'));

export default function App() {
  const [filtros, atualizar] = useState<FiltrosDados>({
    fonte: 'sinan',
    ano: 2026,
    codigoMunicipio: '',
  });
  const cadastro = useApi<Municipio[]>('/municipios');
  const contexto = {
    filtros,
    atualizar,
    municipios: cadastro.dados ?? [],
    cadastroIndisponivel: Boolean(cadastro.erro),
  };

  return (
    <AppLayout>
      <Suspense
        fallback={
          <div className="loading-state" role="status">
            <span className="spinner" />
            Preparando o painel…
          </div>
        }
      >
        <Routes>
          <Route path="/" element={<PanoramaPage {...contexto} />} />
          <Route path="/estimativas" element={<EstimativasPage {...contexto} />} />
          <Route path="/assistente" element={<AssistentePage {...contexto} />} />
          <Route
            path="*"
            element={
              <div className="feedback-state">
                <h1>Página não encontrada</h1>
                <p>Explore os dados a partir do panorama.</p>
                <NavLink to="/" className="button primary">
                  Voltar ao histórico
                </NavLink>
              </div>
            }
          />
        </Routes>
      </Suspense>
    </AppLayout>
  );
}
