import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import { BANNED_WORD, renderedText } from '../../test/copyLaw'
import SectionNav from './SectionNav'

const ITEMS = [
  // The active item is FIRST on purpose: the assertion below reads the active element's own
  // class string, so it must not depend on where the active item sits in the list.
  { key: 'floor', label: 'The floor' },
  { key: 'roster', label: 'Roster' },
]

/** The opening tag of the active destination's own element. */
const activeTag = (markup: string) =>
  markup.match(/<button\b[^>]*aria-selected="true"[^>]*>/)?.[0] ?? ''

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
    // The active element's OWN class string: it carries no rule, and the accent band is drawn
    // inside its edge. Reading the element's tag — not a slice of the markup from the marker
    // onwards — is what makes this independent of the items' order.
    expect(activeTag(html)).not.toContain('rule-b')
  })

  it('draws the accent band inside the active destination’s edge', () => {
    const html = renderToStaticMarkup(<SectionNav items={ITEMS} active="floor" onSelect={() => {}} />)
    expect(activeTag(html)).toContain('shadow-accent-inset')
  })

  it('draws the strip’s rule on the resting destinations', () => {
    const html = renderToStaticMarkup(<SectionNav items={ITEMS} active="floor" onSelect={() => {}} />)
    const resting = html.match(/<button\b[^>]*aria-selected="false"[^>]*>/)?.[0] ?? ''
    expect(resting).toContain('rule-b')
  })

  it('turns the rule to the side when the strip is turned', () => {
    const html = renderToStaticMarkup(
      <SectionNav items={ITEMS} active="floor" onSelect={() => {}} orientation="vertical" />,
    )
    expect(html).toContain('rule-l')
    expect(html).toContain('shadow-accent-inset-left')
  })

  it('renders no banned word — the copy law holds over the kit', () => {
    const html = renderToStaticMarkup(<SectionNav items={ITEMS} active="floor" onSelect={() => {}} />)
    expect(renderedText(html)).not.toMatch(BANNED_WORD)
  })
})
