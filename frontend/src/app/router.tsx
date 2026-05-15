import { Navigate, Route, Routes } from 'react-router-dom';

import AppShell from './AppShell';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';

import ProjectsPage from '../pages/projects/ProjectsPage';
import ProjectCreatePage from '../pages/projects/ProjectCreatePage';

import ProjectOverviewPage from '../pages/workspace/ProjectOverviewPage';
import TopologyPage from '../pages/workspace/TopologyPage';
import AssetsPage from '../pages/workspace/AssetsPage';
import BuildPage from '../pages/workspace/BuildPage';
import SolverPage from '../pages/workspace/SolverPage';
import ResultsPage from '../pages/workspace/ResultsPage';

function wrapPage(page: React.ReactNode) {
  return <ErrorBoundary>{page}</ErrorBoundary>;
}

function AppRouter() {
  return (
    <Routes>
      <Route path="/projects" element={wrapPage(<ProjectsPage />)} />
      <Route path="/projects/new" element={wrapPage(<ProjectCreatePage />)} />
      <Route path="/projects/:projectId" element={<AppShell />}>
        <Route index element={<Navigate to="overview" replace />} />
        <Route path="overview" element={wrapPage(<ProjectOverviewPage />)} />
        <Route path="topology" element={wrapPage(<TopologyPage />)} />
        <Route path="assets" element={wrapPage(<AssetsPage />)} />
        <Route path="build" element={wrapPage(<BuildPage />)} />
        <Route path="solver" element={wrapPage(<SolverPage />)} />
        <Route path="results" element={wrapPage(<ResultsPage />)} />
      </Route>
      <Route path="*" element={<Navigate to="/projects" replace />} />
    </Routes>
  );
}

export { AppRouter };
export default AppRouter;
