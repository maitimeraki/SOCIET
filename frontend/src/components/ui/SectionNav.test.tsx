import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import SectionNav from './SectionNav'

const ITEMS = [
  { key: 'roster', label: 'Roster' },
  { key: 'floor', label: 'The floor' },
]

describe('SectionNav', () => {
  it('is a tablist of buttons, and marks the active destination', () => {
    const html = renderToStaticMarkup(<SectionNav items={ITEMS} active="floor" onSelect={() => {}} />)
    expect(html).toContain('role="tablist"')
    expect(html).toContain('role="tab"')
    expect(html).toContain('aria-selected="true"')
    expect(html).toContain('aria-selected="false"')
  })

  it('is a set of links when the destinations are links', () => {
    const html = renderToStaticMarkup(
      <SectionNav as="links" items={[{ key: 'roster', label: 'Roster', href: '/runs/1/roster' }]} active="roster" />,
    )
    expect(html).toContain('href="/runs/1/roster"')
    expect(html).toContain('aria-current="page"')
    expect(html).not.toContain('role="tab"')
  })

  it('reads the active destination as a cut — the strip’s rule breaks there', () => {
    const html = renderToStaticMarkup(<SectionNav items={ITEMS} active="floor" onSelect={() => {}} />)
    // The active item carries no rule of its own; the accent band is drawn inside its edge.
    expect(html).toContain('shadow-accent-inset')
    const active = html.slice(html.indexOf('aria-selected="true"'))
    expect(active).not.toContain('rule-b')
  })

  it('draws the strip’s rule on the resting destinations', () => {
    const html = renderToStaticMarkup(<SectionNav items={ITEMS} active="floor" onSelect={() => {}} />)
    expect(html).toContain('rule-b')
  })

  it('turns the rule to the side when the strip is turned', () => {
    const html = renderToStaticMarkup(
      <SectionNav items={ITEMS} active="floor" onSelect={() => {}} orientation="vertical" />,
    )
    expect(html).toContain('rule-l')
    expect(html).toContain('shadow-accent-inset-left')
  })
})
