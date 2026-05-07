import { Navigate, Route, Routes } from 'react-router-dom';

import AppShell from './AppShell';

import ProjectsPage from '../pages/projects/ProjectsPage';
import ProjectCreatePage from '../pages/projects/ProjectCreatePage';

import ProjectOverviewPage from '../pages/workspace/ProjectOverviewPage';
import TopologyPage from '../pages/workspace/TopologyPage';
import AssetsPage from '../pages/workspace/AssetsPage';
import BuildPage from '../pages/workspace/BuildPage';
import SolverPage from '../pages/workspace/SolverPage';
import ResultsPage from '../pages/workspace/ResultsPage';

function AppRouter() {
  return (
    <Routes>
      <Route path="/projects" element={<ProjectsPage />} />
      <Route path="/projects/new" element={<ProjectCreatePage />} />
      <Route path="/projects/:projectId" element={<AppShell />}>
        <Route index element={<Navigate to="overview" replace />} />
        <Route path="overview" element={<ProjectOverviewPage />} />
        <Route path="topology" element={<TopologyPage />} />
        <Route path="assets" element={<AssetsPage />} />
        <Route path="build" element={<BuildPage />} />
        <Route path="solver" element={<SolverPage />} />
        <Route path="results" element={<ResultsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/projects" replace />} />
    </Routes>
  );
}

export { AppRouter };
export default AppRouter;
