import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import type { Stance } from '../../run/events'
import { STANCE_ORDER } from '../../run/selectors'
import StanceChip from './StanceChip'
import StanceSymbol from './StanceSymbol'
import Legend from './Legend'

/** The map-legend hue each stance's symbol owns (DSPEC §3.1) — the symbol colour, never the word's. */
const HUE: Record<Stance, string> = {
  POSITIVE: '--color-pos-light',
  NEUTRAL: '--color-neu-light',
  AMBIVALENT: '--color-amb-light',
  NEGATIVE: '--color-neg-light',
}

describe('StanceChip — the legend law', () => {
  it('renders symbol AND colour AND word for every stance, at every size', () => {
    for (const size of ['sm', 'md'] as const) {
      for (const stance of STANCE_ORDER) {
        const html = renderToStaticMarkup(<StanceChip stance={stance} size={size} />)
        expect(html).toContain(`>${stance}<`) // the word
        expect(html).toContain('<svg') // the symbol
        expect(html).toContain(HUE[stance]) // the colour, carried by the symbol
      }
    }
  })

  it('sets the word in ink — a stance hue is a symbol colour and is never text', () => {
    for (const stance of STANCE_ORDER) {
      const html = renderToStaticMarkup(<StanceChip stance={stance} />)
      expect(html).toContain('text-ink')
      expect(html).not.toMatch(/text-stance-/)
    }
  })

  it('is neither a pill nor an outlined box (addendum §7 — the --ink-4 boundary measured 1.88:1)', () => {
    const html = renderToStaticMarkup(<StanceChip stance="POSITIVE" />)
    expect(html).not.toContain('rounded-full')
    expect(html).not.toContain('border-ink-4')
  })
})

describe('StanceSymbol', () => {
  it('gives each stance a different drawn form, not just a different hue', () => {
    const shapes = STANCE_ORDER.map((stance) => renderToStaticMarkup(<StanceSymbol stance={stance} />))
    expect(new Set(shapes).size).toBe(STANCE_ORDER.length)
  })

  it('hides the glyph from assistive tech — the adjacent word carries the meaning', () => {
    expect(renderToStaticMarkup(<StanceSymbol stance="NEGATIVE" />)).toContain('aria-hidden="true"')
  })
})

describe('Legend', () => {
  it('renders a symbol beside every word, so a colour is never the only carrier', () => {
    const html = renderToStaticMarkup(
      <Legend
        title="Stance"
        entries={STANCE_ORDER.map((stance) => ({ symbol: <StanceSymbol stance={stance} />, label: stance }))}
      />,
    )
    expect((html.match(/<svg/g) ?? []).length).toBe(STANCE_ORDER.length)
    for (const stance of STANCE_ORDER) expect(html).toContain(stance)
  })

  it('renders nothing when there is nothing to key', () => {
    expect(renderToStaticMarkup(<Legend entries={[]} />)).toBe('')
  })
})
