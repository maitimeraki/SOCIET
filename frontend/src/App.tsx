import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import AppShell from './components/shell/AppShell'
import AppErrorBoundary from './components/AppErrorBoundary'
import HomePage from './pages/HomePage'
import IngestPage from './pages/IngestPage'
import GraphPage from './pages/GraphPage'
import SocietyPage from './pages/SocietyPage'
import RunPage from './pages/RunPage'
import RunsPage from './pages/RunsPage'
import AgentsPage from './pages/AgentsPage'
import NotFoundPage from './pages/NotFoundPage'

// Route-level boundary: a crash in one page keeps the shell (masthead, nav, health) alive. Keyed on
// the path so navigating elsewhere via the shell clears the fallback without a full reload.
function RoutedContent() {
  const { pathname } = useLocation()
  return (
    <AppErrorBoundary key={pathname}>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/new" element={<Navigate to="/new/ingest" replace />} />
        <Route path="/new/ingest" element={<IngestPage />} />
        <Route path="/new/graph" element={<GraphPage />} />
        <Route path="/new/society" element={<SocietyPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:runId" element={<RunPage />} />
        <Route path="/runs/:runId/:tab" element={<RunPage />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppErrorBoundary>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppShell>
        <RoutedContent />
      </AppShell>
    </BrowserRouter>
  )
}
