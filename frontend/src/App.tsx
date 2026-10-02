import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import AppShell from './components/shell/AppShell'
import HomePage from './pages/HomePage'
import IngestPage from './pages/IngestPage'
import GraphPage from './pages/GraphPage'
import SocietyPage from './pages/SocietyPage'
import RunPage from './pages/RunPage'
import RunsPage from './pages/RunsPage'
import AgentsPage from './pages/AgentsPage'
import NotFoundPage from './pages/NotFoundPage'

export default function App() {
  return (
    <BrowserRouter>
      <AppShell>
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
      </AppShell>
    </BrowserRouter>
  )
}
