import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import AuthLayout from './auth/AuthLayout'
import RequireAuth from './auth/RequireAuth'
import AppShell, { RouteFallback } from './components/shell/AppShell'
import MarketingLayout from './components/shell/MarketingLayout'
import NotFoundPage from './pages/NotFoundPage'

// Each page is its own chunk, so the initial bundle carries only the layouts, the router and the 404 —
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
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const SignInPage = lazy(() => import('./pages/SignInPage'))
const SignUpPage = lazy(() => import('./pages/SignUpPage'))

/**
 * The route tree (plan §1). Three layout routes, so `/` and `/auth/*` render without shell chrome:
 *
 *   MarketingLayout  — public; `/` keeps rendering HomePage for now (Task 17 → LandingPage).
 *   AuthLayout       — public; the sign-in/up surfaces.
 *   RequireAuth      — the guard; wraps AppShell (the chrome) around the authed pages.
 *
 * The top-level `<Suspense>` covers the public layouts' lazy pages. The authed tree carries its own
 * Suspense INSIDE AppShell (see AppShell.tsx), which is what keeps the shell mounted while a page
 * chunk loads — a page swap must not blink the masthead away.
 */
export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route element={<MarketingLayout />}>
            {/* TODO(Task 17): replace HomePage with LandingPage. */}
            <Route path="/" element={<HomePage />} />
          </Route>

          <Route path="/auth" element={<AuthLayout />}>
            <Route index element={<Navigate to="/auth/signin" replace />} />
            <Route path="signin" element={<SignInPage />} />
            <Route path="signup" element={<SignUpPage />} />
          </Route>

          <Route element={<RequireAuth />}>
            <Route element={<AppShell />}>
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/runs" element={<RunsPage />} />
              <Route path="/runs/:runId" element={<RunPage />} />
              <Route path="/runs/:runId/:tab" element={<RunPage />} />
              <Route path="/new" element={<Navigate to="/new/ingest" replace />} />
              <Route path="/new/ingest" element={<IngestPage />} />
              <Route path="/new/graph" element={<GraphPage />} />
              <Route path="/new/society" element={<SocietyPage />} />
              <Route path="/agents" element={<AgentsPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
