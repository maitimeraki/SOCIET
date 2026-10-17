import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): every route is rendered
// to static markup in Node. `App` itself cannot render here — `BrowserRouter` needs a window and the
// pages are `lazy` — so the tree is exercised the way AppShell.test.tsx and RequireAuth.test.tsx
// already do: replicate the guard + route shape under `MemoryRouter` and render the real elements.
//
// `<Navigate>` does not navigate under SSR (RequireAuth.test.tsx:2), so the guard's next-preserving
// redirect cannot be asserted by rendering it. It is pinned through the guard's OWN contract —
// `resolveGuard`/`signInTarget` in src/auth/guard.ts — for the section paths, and the static-markup
// pass proves each path renders its section inside the guard.
import type { ComponentType } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { AuthStatus } from '../auth/authStore'
import { resolveGuard, signInTarget } from '../auth/guard'
import { GuardView } from '../auth/RequireAuth'
import AppShell from '../components/shell/AppShell'
import DocumentsSection from '../sections/DocumentsSection'
import PanelSection from '../sections/PanelSection'
import ResultsSection from '../sections/ResultsSection'
import RunsSection from '../sections/RunsSection'

/** D16: the rail's label and the route's path deliberately differ — the path is exempt from §13. */
const SECTIONS: { path: string; heading: string; Component: ComponentType }[] = [
  { path: '/documents', heading: 'Documents', Component: DocumentsSection },
  { path: '/runs', heading: 'Decisions', Component: RunsSection },
  { path: '/results', heading: 'Verdicts', Component: ResultsSection },
  { path: '/panel', heading: 'Panel', Component: PanelSection },
]

/** The section rendered through the real guard, its decision supplied as a prop (zustand v5's SSR
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

describe.each(SECTIONS)('$path — the $heading section', ({ path, heading, Component }) => {
  it('renders its section inside the guard when the visitor is authed', () => {
    expect(renderGuarded('authed', path, Component)).toContain(heading)
  })

  it('renders neither the section nor a sign-in page while the session is unknown', () => {
    const html = renderGuarded('unknown', path, Component)
    expect(html).not.toContain(heading)
    expect(html).toContain('Checking your session')
  })

  it('renders no section for an anon visitor — the guard redirects (a Navigate, inert under SSR)', () => {
    const html = renderGuarded('anon', path, Component)
    expect(html).not.toContain(heading)
    expect(html).not.toContain('Checking your session')
  })
})

describe('the guard preserves the path a signed-out visitor was reaching for', () => {
  it('anon resolves to a redirect', () => {
    expect(resolveGuard('anon')).toBe('redirect')
  })

  it.each(SECTIONS)('$path → sign-in carrying next=$path', ({ path }) => {
    expect(signInTarget(path, '')).toBe(`/auth/signin?next=${encodeURIComponent(path)}`)
  })
})

describe('the rail marks the section the visitor is in', () => {
  it.each(SECTIONS)('$path marks its own item current', ({ path }) => {
    expect(currentHref(renderShell(path))).toBe(path)
  })
})
