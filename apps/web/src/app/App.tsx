import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { AppShell } from '../components/AppShell';
import { AdminPage } from '../pages/AdminPage';
import { AuthPage } from '../pages/AuthPage';
import { BackupPage } from '../pages/BackupPage';
import { ComparePage } from '../pages/ComparePage';
import { DashboardPage } from '../pages/DashboardPage';
import { DirectionMapPage } from '../pages/DirectionMapPage';
import { EvaluationsPage } from '../pages/EvaluationsPage';
import { GapsPage } from '../pages/GapsPage';
import { JobsPage } from '../pages/JobsPage';
import { LibraryPage } from '../pages/LibraryPage';
import { PaperPage } from '../pages/PaperPage';
import { PlansPage } from '../pages/PlansPage';
import { ProfilePage } from '../pages/ProfilePage';
import { ProjectsPage } from '../pages/ProjectsPage';
import { SearchPage } from '../pages/SearchPage';
import { SettingsPage } from '../pages/SettingsPage';
import { SourcesPage } from '../pages/SourcesPage';

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 15_000 } } });

function ProtectedRoutes() {
  const { token, user } = useAuth();
  if (!token) return <Navigate to="/auth" replace />;
  return <Routes><Route element={<AppShell />}><Route index element={<DashboardPage />} /><Route path="profile" element={<ProfilePage />} /><Route path="projects" element={<ProjectsPage />} /><Route path="search" element={<SearchPage />} /><Route path="papers/:paperId" element={<PaperPage />} /><Route path="library" element={<LibraryPage />} /><Route path="compare" element={<ComparePage />} /><Route path="gaps" element={<GapsPage />} /><Route path="plans" element={<PlansPage />} /><Route path="jobs" element={<JobsPage />} /><Route path="direction-map" element={<DirectionMapPage />} /><Route path="evaluations" element={<EvaluationsPage />} /><Route path="sources" element={<SourcesPage />} /><Route path="settings" element={<SettingsPage />} />{user?.is_admin && <><Route path="backup" element={<BackupPage />} /><Route path="admin" element={<AdminPage />} /></>}</Route></Routes>;
}

export function App() {
  const { token } = useAuth();
  return <QueryClientProvider client={queryClient}>{token ? <ProtectedRoutes /> : <Routes><Route path="*" element={<AuthPage />} /></Routes>}</QueryClientProvider>;
}
