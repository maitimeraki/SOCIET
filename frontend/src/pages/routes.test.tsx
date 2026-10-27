import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): every route is rendered
// to static markup in Node. `App` itself cannot render here — `BrowserRouter` needs a window and the
// pages are `lazy` — so the tree is exercised the way AppShell.test.tsx and RequireAuth.test.tsx
// already do: replicate the guard + route shape under `MemoryRouter` and render the real elements.
//
// App.tsx's own nesting — which element sits under which route — is confirmed by reading App.tsx, not
// by rendering it (no test renders `App`; it would suspend on its `lazy()` chunks and emit only the
// fallback). The four retired routes are redirects now: `<Navigate>` does not navigate under SSR, so
// the redirect table itself is pinned here and the browser capture proves where each one lands.
import type { ComponentType } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { AuthStatus } from '../auth/authStore'
import { resolveGuard, signInTarget } from '../auth/guard'
import { GuardView } from '../auth/RequireAuth'
import AppShell from '../components/shell/AppShell'
import DashboardPage from './DashboardPage'
import DocumentsPage from './DocumentsPage'
import RunsPage from './RunsPage'
import ResultsPage from './ResultsPage'
import { dashboardHref, DASHBOARD_ANCHORS, LEGACY_SECTION_REDIRECTS } from './dashboardAnchors'
// §13 — the one copy-law guard (list + stem-tolerant matcher + tag-stripping reader), shared with
// every rendered-string test.
import { BANNED_WORD, renderedText } from '../test/copyLaw'

/** The section rendered through the real guard, its data supplied as a prop (zustand v5's SSR
 *  snapshot is the initial `unknown` state, so a store-driven render could only be asserted as a
 *  splash). */
const renderGuarded = (status: AuthStatus, path: string, Component: ComponentType) =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          element={
            <GuardView status={status} target={signInTarget(path, '')} unreachable={false} onRetry={() => {}} />
          }
        >
          <Route path={path} element={<Component />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )

/** The shell (and so the rail) at a path, mirroring the authed branch of App.tsx. */
const renderShell = (path: string) =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path={path} element={<p>the child region</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )

/** The href of the one rail item `NavLink` marked current, read from the anchor opening tag. */
function currentHref(html: string): string | undefined {
  const marked = [...html.matchAll(/<a\b([^>]*)>/g)]
    .map((match) => match[1])
    .find((attrs) => attrs.includes('aria-current="page"'))
  return marked?.match(/href="([^"]*)"/)?.[1]
}

describe('the dashboard inside the guard', () => {
  it('renders the one surface when the visitor is authed', () => {
    const html = renderGuarded('authed', '/dashboard', DashboardPage)
    expect(html).toContain('Your account')
    expect(html).toContain('Your material')
    expect(html).toContain('Your decisions')
    expect(html).toContain('The last answer')
    expect(html).toContain('Your panel')
  })

  it('renders neither the dashboard nor a sign-in page while the session is unknown', () => {
    const html = renderGuarded('unknown', '/dashboard', DashboardPage)
    expect(html).not.toContain('Your account')
    expect(html).toContain('Checking your session')
  })

  it('renders no dashboard for an anon visitor — the guard redirects (a Navigate, inert under SSR)', () => {
    const html = renderGuarded('anon', '/dashboard', DashboardPage)
    expect(html).not.toContain('Your account')
    expect(html).not.toContain('Checking your session')
  })
})

describe('the remaining retired route redirects to the dashboard at its anchor (D1)', () => {
  it('maps only /panel now — Documents, Runs and Verdicts are real pages again', () => {
    expect(LEGACY_SECTION_REDIRECTS.map((entry) => entry.path)).toEqual(['/panel'])
    expect(LEGACY_SECTION_REDIRECTS.map((entry) => dashboardHref(entry.anchor))).toEqual(['/dashboard#panel'])
  })

  it('uses the anchors the dashboard actually carries', () => {
    expect(new Set(Object.values(DASHBOARD_ANCHORS)).size).toBe(4)
    expect(dashboardHref(DASHBOARD_ANCHORS.lastAnswer)).toBe('/dashboard#last-answer')
  })
})

describe('the three sections are real pages, not redirects', () => {
  it('renders Documents at /documents', () => {
    expect(renderGuarded('authed', '/documents', DocumentsPage)).toContain('>Documents</h1>')
  })

  it('renders Runs at /runs', () => {
    expect(renderGuarded('authed', '/runs', RunsPage)).toContain('>Runs</h1>')
  })

  it('renders Verdicts at /results', () => {
    expect(renderGuarded('authed', '/results', ResultsPage)).toContain('>Verdicts</h1>')
  })
})

describe('the guard preserves the path a signed-out visitor was reaching for', () => {
  it('anon resolves to a redirect', () => {
    expect(resolveGuard('anon')).toBe('redirect')
  })

  it.each([...LEGACY_SECTION_REDIRECTS.map((entry) => entry.path), '/dashboard'])(
    '%s → sign-in carrying next',
    (path) => {
      expect(signInTarget(path, '')).toBe(`/auth/signin?next=${encodeURIComponent(path)}`)
    },
  )
})

describe('the rail is one item — "Your work"', () => {
  it('marks the dashboard current on /dashboard', () => {
    expect(currentHref(renderShell('/dashboard'))).toBe('/dashboard')
  })

  it('renders exactly one item inside the sections nav', () => {
    const html = renderShell('/dashboard')
    const nav = html.match(/<nav[^>]*aria-label="Sections"[^>]*>[\s\S]*?<\/nav>/)?.[0] ?? ''
    expect(nav.match(/<li>/g) ?? []).toHaveLength(1)
    expect(nav).toContain('Your work')
    expect(nav).not.toContain('Documents')
    expect(nav).not.toContain('Verdicts')
  })
})

describe('the copy-law pattern itself catches banned words, whole-word only', () => {
  it('matches a banned word and its inflections', () => {
    expect(BANNED_WORD.test('an agent here')).toBe(true)
    expect(BANNED_WORD.test('Agents')).toBe(true)
    expect(BANNED_WORD.test('a society of models')).toBe(true)
    expect(BANNED_WORD.test('the chunked rounds')).toBe(true)
  })

  it('does not match a banned word inside a longer one', () => {
    expect(BANNED_WORD.test('bg-ground background ground')).toBe(false)
    expect(BANNED_WORD.test('tookend rundown')).toBe(false)
  })
})

describe('the copy law (§13) holds on the dashboard and the shell', () => {
  it('the dashboard renders no banned word', () => {
    expect(renderedText(renderGuarded('authed', '/dashboard', DashboardPage))).not.toMatch(BANNED_WORD)
  })

  it('renders no banned word in the chrome', () => {
    expect(renderedText(renderShell('/dashboard'))).not.toMatch(BANNED_WORD)
  })
})
