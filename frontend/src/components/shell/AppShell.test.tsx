import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): the shell is rendered to
// static markup in Node. The router pattern mirrors RequireAuth.test.tsx — `<Navigate>` does not
// navigate under SSR, but AppShell renders its `<Outlet/>` directly, so the child route lands in place.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import AppShell from './AppShell'

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

  it('offers a skip link to #content', () => {
    expect(render()).toContain('href="#content"')
  })

  it('marks the current section with aria-current', () => {
    expect(openingTag(render(), 'href="/documents"')).toContain('aria-current="page"')
  })
})
