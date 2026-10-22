/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

/**
 * The tonal ladder, measured (§13.6 Wave 1).
 *
 * The app sits on the page ground: `--color-ground` is the page surface, `--color-ground-2` the
 * band, and every light surface carries its ink and its rule legibly. This parses the tokens out
 * of `index.css` and computes the ratios, so the acceptance is a permanent check and not a
 * one-time measurement.
 */

const css = readFileSync('src/index.css', 'utf8')

/** The `@theme` block's own text — every token measured here is declared there. */
const themeStart = css.indexOf('@theme {')
const theme = css.slice(themeStart, css.indexOf('\n}', themeStart))

/** The `--color-*` declarations, exactly as written. */
const declared = new Map<string, string>()
for (const line of theme.split('\n')) {
  const match = line.match(/^\s*(--color-[a-z0-9-]+):\s*(.+?);/)
  if (match) declared.set(match[1], match[2].trim())
}

/** One level of aliasing: `--color-ground` → `var(--color-page)` → the page's hex. */
function resolve(token: string): string {
  const value = declared.get(token)
  if (value === undefined) throw new Error(`${token} is not declared in @theme`)
  const alias = value.match(/^var\((--color-[a-z0-9-]+)\)$/)
  if (!alias) return value
  const target = declared.get(alias[1])
  if (target === undefined) throw new Error(`${alias[1]} is not declared in @theme`)
  return target
}

/** The WCAG 2.2 relative luminance of a token. */
function luminance(token: string): number {
  const value = resolve(token)
  const hex = value.match(/^#([0-9a-f]{6})$/i)
  if (!hex) throw new Error(`${token} is not a hex colour: ${value}`)
  const n = parseInt(hex[1], 16)
  const channel = (c: number) => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  return (
    0.2126 * channel((n >> 16) & 255) +
    0.7152 * channel((n >> 8) & 255) +
    0.0722 * channel(n & 255)
  )
}

/** The contrast ratio between two tokens (WCAG 2.2). */
function contrast(fg: string, bg: string): number {
  const a = luminance(fg)
  const b = luminance(bg)
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
}

/** The CIE lightness of a token: L* = 116·Y^(1/3) − 16 above the knee, 903.3·Y below it. */
function lightness(token: string): number {
  const y = luminance(token)
  return y > 0.008856 ? 116 * Math.cbrt(y) - 16 : 903.3 * y
}

/** The pairs §13.6 Wave 1 sets a floor on, and what each floor is for. */
const FLOORS = [
  { fg: '--color-canvas', bg: '--color-ground', floor: 1.1, label: 'a card on the page ground' },
  { fg: '--color-ground-2', bg: '--color-ground', floor: 1.1, label: 'the band on the page ground' },
  { fg: '--color-canvas', bg: '--color-ground-2', floor: 1.1, label: 'a card on the band' },
  { fg: '--color-rule', bg: '--color-ground', floor: 3, label: 'a rule on the page ground' },
  { fg: '--color-rule', bg: '--color-ground-2', floor: 3, label: 'a rule on the band' },
  { fg: '--color-rule', bg: '--color-canvas', floor: 3, label: 'a rule on a card' },
  { fg: '--color-rule', bg: '--color-surface-sky', floor: 3, label: 'a rule on the sky band' },
  { fg: '--color-rule', bg: '--color-surface-warm', floor: 3, label: 'a rule on the warm band' },
  { fg: '--color-rule', bg: '--color-surface-plum', floor: 3, label: 'a rule on the plum band' },
  { fg: '--color-ink-3', bg: '--color-ground', floor: 4.5, label: 'a caption on the page ground' },
  { fg: '--color-ink-3', bg: '--color-ground-2', floor: 4.5, label: 'a caption on the band' },
  { fg: '--color-ink-3', bg: '--color-canvas', floor: 4.5, label: 'a caption on a card' },
  { fg: '--color-ink-3', bg: '--color-surface-sky', floor: 4.5, label: 'a caption on the sky band' },
  { fg: '--color-ink-3', bg: '--color-surface-warm', floor: 4.5, label: 'a caption on the warm band' },
  { fg: '--color-ink-3', bg: '--color-surface-plum', floor: 4.5, label: 'a caption on the plum band' },
]

describe('the tonal ladder — the app sits on the page ground', () => {
  it('resolves the ground to the page surface', () => {
    expect(resolve('--color-ground')).toBe('#eceff4')
  })

  it('resolves the band to the named band surface', () => {
    expect(resolve('--color-ground-2')).toBe('#dfe4ec')
  })

  it.each(FLOORS)('$label clears $floor:1', ({ fg, bg, floor }) => {
    expect(contrast(fg, bg)).toBeGreaterThanOrEqual(floor)
  })

  it('spreads the map ramp at least 8 L* apart', () => {
    const spread = Math.abs(lightness('--color-map-ground-2') - lightness('--color-map-ground'))
    expect(spread).toBeGreaterThanOrEqual(8)
  })
})
