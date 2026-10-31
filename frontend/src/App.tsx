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
// The homepage DEMO — the review copy of the page, from `docs/FRONTEND_DESIGN_REVIEW.md` §2.1,
// kept behind its own route until the owner signs off and it is retired.
const HomeDemo = lazy(() => import('./marketing/HomeDemo'))
const NewRunWorkspace = lazy(() => import('./pages/NewRunWorkspace'))
const RunPage = lazy(() => import('./pages/RunPage'))
const WorkspaceShell = lazy(() => import('./components/shell/WorkspaceShell'))
const AgentsPage = lazy(() => import('./pages/AgentsPage'))
const OverviewPage = lazy(() => import('./pages/OverviewPage'))
const DocumentsPage = lazy(() => import('./pages/DocumentsPage'))
const RunsPage = lazy(() => import('./pages/RunsPage'))
const ResultsPage = lazy(() => import('./pages/ResultsPage'))
const LandingPage = lazy(() => import('./pages/LandingPage'))
const SignInPage = lazy(() => import('./pages/SignInPage'))
const SignUpPage = lazy(() => import('./pages/SignUpPage'))
const PricingPage = lazy(() => import('./pages/PricingPage'))

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
            <Route path="/pricing" element={<PricingPage />} />
            <Route path="/demo-home" element={<HomeDemo />} />
          </Route>

          <Route path="/auth" element={<AuthLayout />}>
            <Route index element={<Navigate to="/auth/signin" replace />} />
            <Route path="signin" element={<SignInPage />} />
            <Route path="signup" element={<SignUpPage />} />
          </Route>

          <Route element={<RequireAuth />}>
            {/* The bare post-auth address (`DEFAULT_NEXT`): a sibling of the shells, so no rail or
                workspace chrome flashes before the account state picks a destination. */}
            <Route path="/landing" element={<LandingPage />} />
            {/* §9 The full-screen workspace: the new-decision lifecycle and every run share one shell,
                so the one map host is mounted above the pages and never remounted by a page change.
                The old per-step paths stay valid routes as redirects into `/new`, carrying the step
                as `?step=` — eight existing call sites depend on them, and nothing may 404. */}
            <Route element={<WorkspaceShell />}>
              <Route path="/new" element={<NewRunWorkspace />} />
              <Route path="/new/ingest" element={<Navigate to="/new?step=ingest" replace />} />
              <Route path="/new/graph" element={<Navigate to="/new?step=graph" replace />} />
              <Route path="/new/society" element={<Navigate to="/new?step=society" replace />} />
              <Route path="/runs/:runId" element={<RunPage />} />
              <Route path="/runs/:runId/:tab" element={<RunPage />} />
            </Route>
            <Route element={<AppShell />}>
              <Route path="/overview" element={<OverviewPage />} />
              <Route path="/documents" element={<DocumentsPage />} />
              <Route path="/runs" element={<RunsPage />} />
              <Route path="/results" element={<ResultsPage />} />
              {/* The one-page dashboard is retired; its old anchors land on the Overview. */}
              <Route path="/dashboard" element={<Navigate to="/overview" replace />} />
              <Route path="/panel" element={<Navigate to="/overview" replace />} />
              <Route path="/agents" element={<AgentsPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
