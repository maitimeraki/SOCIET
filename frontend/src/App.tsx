import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import AppShell from './components/shell/AppShell'
import AppErrorBoundary from './components/AppErrorBoundary'
import Skeleton from './components/ui/Skeleton'
import NotFoundPage from './pages/NotFoundPage'

// Each page is its own chunk, so the initial bundle carries only the shell, the router and the 404 —
// Sigma/graphology/framer-motion leave the entry chunk entirely. Specifiers stay static literals: a
// computed path would defeat Vite's deterministic split. NotFoundPage stays eager (12 lines, no heavy
// imports) so a mistyped URL never waits on a chunk fetch to say "not found".
const HomePage = lazy(() => import('./pages/HomePage'))
const IngestPage = lazy(() => import('./pages/IngestPage'))
const GraphPage = lazy(() => import('./pages/GraphPage'))
const SocietyPage = lazy(() => import('./pages/SocietyPage'))
const RunPage = lazy(() => import('./pages/RunPage'))
const RunsPage = lazy(() => import('./pages/RunsPage'))
const AgentsPage = lazy(() => import('./pages/AgentsPage'))

/** The page-chunk loading state — the same pulse skeleton the pages use, so the swap is seamless. */
function RouteFallback() {
  return (
    <div role="status" aria-live="polite" className="flex flex-col gap-3">
      <span className="sr-only">Loading…</span>
      <Skeleton className="h-7 w-52" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-3/4" />
    </div>
  )
}

// Route-level boundary: a crash in one page keeps the shell (masthead, nav, health) alive. Keyed on
// the path so navigating elsewhere via the shell clears the fallback without a full reload.
function RoutedContent() {
  const { pathname } = useLocation()
  return (
    <AppErrorBoundary key={pathname}>
      <Suspense fallback={<RouteFallback />}>
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
      </Suspense>
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
