import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): the shell is rendered to
// static markup in Node. The router pattern mirrors RequireAuth.test.tsx — `<Navigate>` does not
// navigate under SSR, but AppShell renders its `<Outlet/>` directly, so the child route lands in place.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import AppShell, { boundaryKey } from './AppShell'

const render = () =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={['/documents']}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/documents" element={<p>the child region</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )

/** The opening tag of the first anchor whose attributes match, so an assertion lands on one link. */
function openingTag(html: string, match: string): string {
  const tag = html.split('<a ').slice(1).find((a) => a.slice(0, a.indexOf('>')).includes(match))
  return tag ? tag.slice(0, tag.indexOf('>')) : ''
}

describe('AppShell', () => {
  it('renders the rail as a nav with an accessible name', () => {
    expect(render()).toMatch(/<nav[^>]*aria-label="Sections"/)
  })

  it('renders the routed child inside main#content', () => {
    const html = render()
    expect(html).toContain('<main id="content"')
    expect(html.indexOf('<main id="content"')).toBeLessThan(html.indexOf('the child region'))
  })

  it('caps and centres the content column at 1320px (§6.2)', () => {
    const main = render().match(/<main[^>]*id="content"[^>]*>/)?.[0] ?? ''
    expect(main).toContain('max-w-[1320px]')
    expect(main).toContain('mx-auto')
  })

  it('offers a skip link to #content', () => {
    expect(render()).toContain('href="#content"')
  })

  it('marks the current section with aria-current', () => {
    expect(openingTag(render(), 'href="/documents"')).toContain('aria-current="page"')
  })

  it('keeps the account foot outside the sections landmark', () => {
    const html = render()
    expect(html.indexOf('</nav>')).toBeLessThan(html.indexOf('Account'))
  })
})

describe('boundaryKey — a run remounts by run, not by tab (§14.4 row 12)', () => {
  it('shares one key across the tabs and steps of the same run', () => {
    expect(boundaryKey('/runs/run-a/roster')).toBe(boundaryKey('/runs/run-a/verdict'))
    expect(boundaryKey('/runs/run-a')).toBe(boundaryKey('/runs/run-a/floor'))
  })

  it('gives different runs different keys', () => {
    expect(boundaryKey('/runs/run-a/roster')).not.toBe(boundaryKey('/runs/run-b/roster'))
    expect(boundaryKey('/runs/run-a')).not.toBe(boundaryKey('/runs/run-b'))
  })

  it('keeps each top-level route on its own single-segment key', () => {
    expect(boundaryKey('/')).toBe('')
    expect(boundaryKey('/dashboard')).toBe('dashboard')
    expect(boundaryKey('/new')).toBe('new')
    expect(boundaryKey('/dashboard')).not.toBe(boundaryKey('/new'))
  })

  it('does not throw on a short or malformed path', () => {
    expect(() => boundaryKey('')).not.toThrow()
    expect(boundaryKey('')).toBe('')
    expect(boundaryKey('//')).toBe('')
    expect(boundaryKey('/runs')).toBe('runs')
    expect(boundaryKey('/runs/')).toBe('runs')
    expect(boundaryKey('/runs//roster')).toBe('runs/roster')
  })
})
