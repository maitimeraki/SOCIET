import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): every route is rendered
// to static markup in Node. `App` itself cannot render here — `BrowserRouter` needs a window and the
// pages are `lazy` — so the tree is exercised the way AppShell.test.tsx and RequireAuth.test.tsx
// already do: replicate the guard + route shape under `MemoryRouter` and render the real elements.
//
// App.tsx's own nesting — which element sits under which route — is confirmed by reading App.tsx, not
// by rendering it (no test renders `App`; it would suspend on its `lazy()` chunks and emit only the
// fallback). The two retired routes are redirects now: `<Navigate>` is inert under SSR, so the
// redirect routes are pinned by reading App.tsx's source here; no browser pass was run to observe
// where they land.
import { readFileSync } from 'node:fs'
import type { ComponentType } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { AuthStatus } from '../auth/authStore'
import { resolveGuard, signInTarget } from '../auth/guard'
import { GuardView } from '../auth/RequireAuth'
import AppShell from '../components/shell/AppShell'
import DocumentsPage from './DocumentsPage'
import RunsPage from './RunsPage'
import ResultsPage from './ResultsPage'
// §13 — the one copy-law guard (list + stem-tolerant matcher + tag-stripping reader), shared with
// every rendered-string test.
import { BANNED_TERMS, BANNED_WORD, renderedText } from '../test/copyLaw'

const appSource = readFileSync('src/App.tsx', 'utf8')

/** A `<Route path="…" element={<Navigate to="/overview" replace />} />`, whitespace tolerated. */
const redirectsToOverview = (path: string) =>
  new RegExp(`<Route\\s+path="${path}"\\s+element=\\{<Navigate\\s+to="/overview"\\s+replace\\s*/>\\}\\s*/>`).test(appSource)

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

describe('the retired routes redirect into the overview', () => {
  it.each(['/dashboard', '/panel'])('%s redirects to /overview', (path) => {
    expect(redirectsToOverview(path)).toBe(true)
  })

  it('no longer imports or renders the one-page dashboard', () => {
    expect(appSource).not.toContain('DashboardPage')
    expect(appSource).not.toContain('dashboardAnchors')
  })

  it('keeps the 404 for unknown shell paths', () => {
    expect(appSource).toContain('<Route path="*" element={<NotFoundPage />} />')
  })
})

describe('a section page inside the guard', () => {
  it('renders the page when the visitor is authed', () => {
    expect(renderGuarded('authed', '/documents', DocumentsPage)).toContain('>Your material</h1>')
  })

  it('renders neither the page nor a sign-in page while the session is unknown', () => {
    const html = renderGuarded('unknown', '/documents', DocumentsPage)
    expect(html).not.toContain('>Your material</h1>')
    expect(html).toContain('Checking your session')
  })

  it('renders no page for an anon visitor — the guard redirects (a Navigate, inert under SSR)', () => {
    const html = renderGuarded('anon', '/documents', DocumentsPage)
    expect(html).not.toContain('>Your material</h1>')
    expect(html).not.toContain('Checking your session')
  })
})

describe('the three sections are real pages, not redirects', () => {
  it('renders Documents at /documents', () => {
    expect(renderGuarded('authed', '/documents', DocumentsPage)).toContain('>Your material</h1>')
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

  it.each(['/dashboard', '/panel', '/documents', '/runs', '/results'])('%s → sign-in carrying next', (path) => {
    expect(signInTarget(path, '')).toBe(`/auth/signin?next=${encodeURIComponent(path)}`)
  })
})

describe('the rail carries the four destinations', () => {
  it.each([
    ['/overview', 'Overview'],
    ['/documents', 'Documents'],
    ['/runs', 'Runs'],
    ['/results', 'Verdict'],
  ])('marks %s current at its own path', (path, label) => {
    const html = renderShell(path)
    expect(currentHref(html)).toBe(path)
    expect(html).toContain(label)
  })

  it('lists them in the order the work happens', () => {
    const html = renderShell('/overview')
    const nav = html.match(/<nav[^>]*aria-label="Sections"[^>]*>[\s\S]*?<\/nav>/)?.[0] ?? ''
    const order = ['Overview', 'Documents', 'Runs', 'Verdict'].map((label) => nav.indexOf(label))
    expect(order).toEqual([...order].sort((a, b) => a - b))
    expect(nav.match(/<li>/g) ?? []).toHaveLength(4)
  })

  it('offers the new-decision action, then a real sign-out', () => {
    const html = renderShell('/overview')
    const nav = html.match(/<nav[^>]*aria-label="Sections"[^>]*>[\s\S]*?<\/nav>/)?.[0] ?? ''
    expect(nav).toContain('href="/new"')
    expect(nav.indexOf('New decision')).toBeGreaterThan(nav.indexOf('Societas'))
    expect(html).toContain('Sign out')
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
    expect(BANNED_WORD.test('bg-bone background ground')).toBe(false)
    expect(BANNED_WORD.test('tookend rundown')).toBe(false)
  })
})

describe('the copy law (§13) holds on the shell routes', () => {
  it.each(['/documents', '/runs', '/results'])('renders no banned word in the chrome at %s', (path) => {
    expect(renderedText(renderShell(path))).not.toMatch(BANNED_TERMS)
  })
})
