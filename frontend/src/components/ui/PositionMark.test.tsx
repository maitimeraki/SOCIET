import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo: render to static markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import PositionMark, { PositionGlyph, stanceWord } from './PositionMark'

const POSITIONS = ['POSITIVE', 'NEUTRAL', 'AMBIVALENT', 'NEGATIVE'] as const

/** §4.6's symbols — the symbol is the character, never a picture. */
const SYMBOL: Record<(typeof POSITIONS)[number], string> = {
  POSITIVE: '▲',
  NEUTRAL: '●',
  AMBIVALENT: '◐',
  NEGATIVE: '▼',
}

describe('the position mark', () => {
  it.each(POSITIONS)('names %s in words, not in enum case', (position) => {
    const html = renderToStaticMarkup(<PositionMark position={position} ground="light" />)
    const word = stanceWord(position)
    expect(html).toContain(word)
    expect(html).not.toContain(`>${position}<`)
  })

  it.each(POSITIONS)('draws a symbol for %s', (position) => {
    const html = renderToStaticMarkup(<PositionGlyph position={position} ground="light" />)
    expect(html).toContain(SYMBOL[position])
    expect(html).toContain('aria-hidden="true"')
  })

  it('never draws the mark in the accent alone — the word is always ink', () => {
    const html = renderToStaticMarkup(<PositionMark position="NEGATIVE" ground="light" />)
    expect(html).toContain('text-ink')
  })

  it('wears the map ramp on the map and the light ramp on the light ground', () => {
    const onMap = renderToStaticMarkup(<PositionMark position="POSITIVE" ground="map" />)
    expect(onMap).toContain('text-map-ink')
    expect(renderToStaticMarkup(<PositionGlyph position="POSITIVE" ground="map" />)).toContain(
      'var(--color-pos)',
    )
    expect(renderToStaticMarkup(<PositionGlyph position="POSITIVE" ground="light" />)).toContain(
      'var(--color-pos-light)',
    )
  })

  it('returns the raw string for empty or unrecognised input, never "undefined"', () => {
    expect(stanceWord('')).toBe('')
    expect(stanceWord('MAROON')).toBe('MAROON')
  })
})
