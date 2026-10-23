import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import { BANNED_WORD, renderedText } from '../../test/copyLaw'
import type { Stance } from '../../run/events'
import { STANCE_ORDER } from '../../run/selectors'
import PositionMark, { PositionGlyph } from './PositionMark'

/** The light-ground hue each position's symbol owns — the symbol colour, never the word's. */
const LIGHT_HUE: Record<Stance, string> = {
  POSITIVE: '--color-pos-light',
  NEUTRAL: '--color-neu-light',
  AMBIVALENT: '--color-amb-light',
  NEGATIVE: '--color-neg-light',
}

describe('PositionMark — the legend law', () => {
  it('renders symbol AND colour AND word for every position, at every size', () => {
    for (const size of ['sm', 'md'] as const) {
      for (const stance of STANCE_ORDER) {
        const html = renderToStaticMarkup(<PositionMark position={stance} size={size} ground="light" />)
        expect(html).toContain(`>${stance}<`) // the word
        expect(html).toContain('<svg') // the symbol
        expect(html).toContain(LIGHT_HUE[stance]) // the colour, carried by the symbol
      }
    }
  })

  it('sets the word in ink — a position hue is a symbol colour and is never text', () => {
    for (const stance of STANCE_ORDER) {
      const html = renderToStaticMarkup(<PositionMark position={stance} ground="light" />)
      expect(html).toContain('text-ink')
      expect(html).not.toMatch(/text-stance-/)
    }
  })

  it('is neither a pill nor an outlined box', () => {
    const html = renderToStaticMarkup(<PositionMark position="POSITIVE" ground="light" />)
    expect(html).not.toContain('rounded-full')
    expect(html).not.toContain('border-ink-4')
  })

  it('gives each position a different drawn form, not just a different hue', () => {
    const shapes = STANCE_ORDER.map((stance) =>
      renderToStaticMarkup(<PositionGlyph position={stance} ground="light" />),
    )
    expect(new Set(shapes).size).toBe(STANCE_ORDER.length)
  })

  it('hides the glyph from assistive tech — the adjacent word carries the meaning', () => {
    expect(renderToStaticMarkup(<PositionGlyph position="NEGATIVE" ground="light" />)).toContain(
      'aria-hidden="true"',
    )
  })

  it('wears the map ramp on the map ground, and the light ramp on the light ground', () => {
    const onMap = renderToStaticMarkup(<PositionMark position="POSITIVE" ground="map" />)
    expect(onMap).toContain('var(--color-pos)')
    expect(onMap).toContain('text-map-ink')

    const onLight = renderToStaticMarkup(<PositionMark position="POSITIVE" ground="light" />)
    expect(onLight).toContain('var(--color-pos-light)')
    expect(onLight).not.toContain('var(--color-pos)')
  })

  it('gives every position a word — a mark with no adjacent word is a bug', () => {
    for (const stance of STANCE_ORDER) {
      const html = renderToStaticMarkup(<PositionMark position={stance} ground="light" />)
      expect(html).toContain(`>${stance}<`)
    }
  })

  it('renders no banned word — the copy law holds over the kit', () => {
    for (const stance of STANCE_ORDER) {
      const html = renderToStaticMarkup(<PositionMark position={stance} ground="light" />)
      expect(renderedText(html)).not.toMatch(BANNED_WORD)
    }
  })
})
