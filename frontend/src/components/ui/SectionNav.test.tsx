import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import { BANNED_TERMS, renderedText } from '../../test/copyLaw'
import SectionNav, { rovingIndex } from './SectionNav'

const ITEMS = [
  // The active item is FIRST on purpose: the assertion below reads the active element's own
  // class string, so it must not depend on where the active item sits in the list.
  { key: 'floor', label: 'The floor' },
  { key: 'roster', label: 'Roster' },
]

/** The opening tag of the active destination's own element. */
const activeTag = (markup: string) =>
  markup.match(/<button\b[^>]*aria-selected="true"[^>]*>/)?.[0] ?? ''

/** The opening tag of the first resting destination's own element. */
const restingTag = (markup: string) =>
  markup.match(/<button\b[^>]*aria-selected="false"[^>]*>/)?.[0] ?? ''

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
    expect(renderedText(html)).not.toMatch(BANNED_TERMS)
  })
})

describe('SectionNav is a real tablist (§14.4)', () => {
  it('ties each tab to its panel through ids derived from the prefix', () => {
    const html = renderToStaticMarkup(<SectionNav idPrefix="run" items={ITEMS} active="floor" onSelect={() => {}} />)
    expect(activeTag(html)).toContain('id="run-tab-floor"')
    expect(activeTag(html)).toContain('aria-controls="run-panel-floor"')
    expect(restingTag(html)).toContain('id="run-tab-roster"')
    expect(restingTag(html)).toContain('aria-controls="run-panel-roster"')
  })

  it('puts only the active tab in the tab order', () => {
    const html = renderToStaticMarkup(<SectionNav items={ITEMS} active="floor" onSelect={() => {}} />)
    expect(activeTag(html)).toContain('tabindex="0"')
    expect(restingTag(html)).toContain('tabindex="-1"')
  })

  it('declares its orientation on the tablist', () => {
    const horizontal = renderToStaticMarkup(<SectionNav items={ITEMS} active="floor" onSelect={() => {}} />)
    const vertical = renderToStaticMarkup(
      <SectionNav items={ITEMS} active="floor" onSelect={() => {}} orientation="vertical" />,
    )
    expect(horizontal).toContain('aria-orientation="horizontal"')
    expect(vertical).toContain('aria-orientation="vertical"')
  })

  it('moves roving focus with the arrows, wrapping at both ends', () => {
    expect(rovingIndex('ArrowRight', 0, 3, false)).toBe(1)
    expect(rovingIndex('ArrowRight', 2, 3, false)).toBe(0)
    expect(rovingIndex('ArrowLeft', 0, 3, false)).toBe(2)
    expect(rovingIndex('ArrowLeft', 2, 3, false)).toBe(1)
  })

  it('jumps to the ends with Home and End', () => {
    expect(rovingIndex('Home', 2, 5, false)).toBe(0)
    expect(rovingIndex('End', 1, 5, false)).toBe(4)
  })

  it('uses the vertical arrows when the strip is turned, and ignores the wrong axis', () => {
    expect(rovingIndex('ArrowDown', 0, 3, true)).toBe(1)
    expect(rovingIndex('ArrowUp', 0, 3, true)).toBe(2)
    expect(rovingIndex('ArrowRight', 0, 3, true)).toBeNull()
    expect(rovingIndex('ArrowDown', 0, 3, false)).toBeNull()
  })

  it('leaves other keys to the platform', () => {
    expect(rovingIndex('Tab', 0, 3, false)).toBeNull()
    expect(rovingIndex('Enter', 0, 3, false)).toBeNull()
  })
})
