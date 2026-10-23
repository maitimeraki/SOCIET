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
const Hero = lazy(() => import('./marketing/Hero'))
// The homepage DEMO — the target design from `docs/FRONTEND_DESIGN_REVIEW.md` §2.1, built as a
// preview and kept until the owner signs off. It is scoped to its own tokens
// (`marketing/home-demo.css`), so it changes nothing about the shipped `/` or any other surface.
const HomeDemo = lazy(() => import('./marketing/HomeDemo'))
const NewRunWorkspace = lazy(() => import('./pages/NewRunWorkspace'))
const RunPage = lazy(() => import('./pages/RunPage'))
const DocumentsSection = lazy(() => import('./sections/DocumentsSection'))
const RunsSection = lazy(() => import('./sections/RunsSection'))
const ResultsSection = lazy(() => import('./sections/ResultsSection'))
const PanelSection = lazy(() => import('./sections/PanelSection'))
const AgentsPage = lazy(() => import('./pages/AgentsPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const SignInPage = lazy(() => import('./pages/SignInPage'))
const SignUpPage = lazy(() => import('./pages/SignUpPage'))

/**
 * The route tree (plan §1). Three layout routes, so `/` and `/auth/*` render without shell chrome:
 *
 *   MarketingLayout  — public; `/` renders the homepage (Hero).
 *   AuthLayout       — public; the sign-in/up surfaces.
 *   RequireAuth      — the guard; wraps AppShell (the chrome) around the authed pages.
 *
 * The top-level `<Suspense>` covers the public layouts' lazy pages. The authed tree carries its own
 * Suspense INSIDE AppShell (see AppShell.tsx), which is what keeps the shell mounted while a page
 * chunk loads — a page swap must not blink the rail away.
 */
export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route element={<MarketingLayout />}>
            <Route path="/" element={<Hero />} />
            <Route path="/demo-home" element={<HomeDemo />} />
          </Route>

          <Route path="/auth" element={<AuthLayout />}>
            <Route index element={<Navigate to="/auth/signin" replace />} />
            <Route path="signin" element={<SignInPage />} />
            <Route path="signup" element={<SignUpPage />} />
          </Route>

          <Route element={<RequireAuth />}>
            <Route element={<AppShell />}>
              <Route path="/dashboard" element={<DashboardPage />} />
              {/* The rail's four destinations (D16): the label differs from the path on purpose. */}
              <Route path="/documents" element={<DocumentsSection />} />
              <Route path="/runs" element={<RunsSection />} />
              <Route path="/runs/:runId" element={<RunPage />} />
              <Route path="/runs/:runId/:tab" element={<RunPage />} />
              <Route path="/results" element={<ResultsSection />} />
              <Route path="/panel" element={<PanelSection />} />
              {/* §9 one workspace, three steps (Ruling F22). `/new` renders the workspace; the old
                  per-step paths stay valid routes as redirects into it, carrying the step as `?step=`
                  — eight existing call sites navigate to them, and nothing may 404. */}
              <Route path="/new" element={<NewRunWorkspace />} />
              <Route path="/new/ingest" element={<Navigate to="/new?step=ingest" replace />} />
              <Route path="/new/graph" element={<Navigate to="/new?step=graph" replace />} />
              <Route path="/new/society" element={<Navigate to="/new?step=society" replace />} />
              <Route path="/agents" element={<AgentsPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
