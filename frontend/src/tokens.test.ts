/// <reference types="node" />
import { readFileSync, readdirSync } from 'node:fs'
import { basename, join } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * The Quiet Room tonal ladder, measured (§4).
 *
 * `index.css` declares every token in one `@theme` block. This parses that block, resolves the
 * one level of aliasing it allows, and computes the WCAG 2.2 ratios — so the acceptance is a
 * permanent check, not a one-time measurement.
 */

const css = readFileSync('src/index.css', 'utf8')

const themeStart = css.indexOf('@theme {')
const theme = css.slice(themeStart, css.indexOf('\n}', themeStart))

const declared = new Map<string, string>()
for (const match of theme.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) {
  declared.set(match[1], match[2].trim())
}

/** One level of aliasing: `--color-x` → `var(--color-y)` → the hex. */
function resolve(token: string): string {
  const value = declared.get(token)
  if (value === undefined) throw new Error(`${token} is not declared in @theme`)
  const alias = value.match(/^var\((--[a-z0-9-]+)\)$/)
  if (!alias) return value
  const target = declared.get(alias[1])
  if (target === undefined) throw new Error(`${alias[1]} is not declared in @theme`)
  return target
}

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

/** The floors §4 sets, and what each one is for. Body text 4.5, boundaries and large text 3. */
const FLOORS = [
  { fg: '--color-ink', bg: '--color-bone', floor: 4.5, label: 'a heading on bone' },
  { fg: '--color-ink', bg: '--color-paper', floor: 4.5, label: 'a heading on paper' },
  { fg: '--color-ink-2', bg: '--color-bone', floor: 4.5, label: 'body copy on bone' },
  { fg: '--color-ink-2', bg: '--color-sand', floor: 4.5, label: 'body copy on sand' },
  { fg: '--color-ink-3', bg: '--color-bone', floor: 4.5, label: 'a caption on bone' },
  { fg: '--color-ink-3', bg: '--color-paper', floor: 4.5, label: 'a caption on paper' },
  { fg: '--color-ink-3', bg: '--color-sand', floor: 4.5, label: 'a caption on sand' },
  { fg: '--color-rule', bg: '--color-bone', floor: 3, label: 'a record rule on bone' },
  { fg: '--color-rule', bg: '--color-paper', floor: 3, label: 'a record rule on paper' },
  { fg: '--color-rule', bg: '--color-sand', floor: 3, label: 'a record rule on sand' },
  { fg: '--color-accent', bg: '--color-bone', floor: 4.5, label: 'an accent label on bone' },
  { fg: '--color-accent', bg: '--color-paper', floor: 4.5, label: 'an accent label on paper' },
  { fg: '--color-accent', bg: '--color-sand', floor: 4.5, label: 'an accent label on sand' },
  { fg: '--color-on-accent', bg: '--color-accent', floor: 4.5, label: 'a label on an accent fill' },
  { fg: '--color-on-accent', bg: '--color-accent-press', floor: 4.5, label: 'a label on a pressed accent' },
  { fg: '--color-ok', bg: '--color-paper', floor: 4.5, label: 'a verified mark on paper' },
  { fg: '--color-warn', bg: '--color-bone', floor: 4.5, label: 'a caution mark on bone' },
  { fg: '--color-danger', bg: '--color-paper', floor: 4.5, label: 'a danger mark on paper' },
  { fg: '--color-caution', bg: '--color-bone', floor: 4.5, label: 'the case against on bone' },
  { fg: '--color-caution', bg: '--color-paper', floor: 4.5, label: 'the case against on paper' },
  { fg: '--color-map-ink', bg: '--color-map-ground', floor: 4.5, label: 'map text on pine' },
  { fg: '--color-map-ink-2', bg: '--color-map-ground', floor: 4.5, label: 'map secondary text on pine' },
  { fg: '--color-map-accent', bg: '--color-map-ground', floor: 4.5, label: 'the map live mark on pine' },
  { fg: '--color-pos-light', bg: '--color-bone', floor: 4.5, label: 'a positive mark on bone' },
  { fg: '--color-neu-light', bg: '--color-bone', floor: 4.5, label: 'a neutral mark on bone' },
  { fg: '--color-amb-light', bg: '--color-bone', floor: 4.5, label: 'an ambivalent mark on bone' },
  { fg: '--color-neg-light', bg: '--color-bone', floor: 4.5, label: 'a negative mark on bone' },
  { fg: '--color-pos', bg: '--color-map-ground', floor: 4.5, label: 'a positive mark on pine' },
  { fg: '--color-neu', bg: '--color-map-ground', floor: 4.5, label: 'a neutral mark on pine' },
  { fg: '--color-amb', bg: '--color-map-ground', floor: 4.5, label: 'an ambivalent mark on pine' },
  { fg: '--color-neg', bg: '--color-map-ground', floor: 4.5, label: 'a negative mark on pine' },
]

/** Every token name and class name the Quiet Room retired. None may survive. */
const RETIRED = [
  '--color-ground',
  '--color-ground-2',
  '--color-canvas',
  '--color-border',
  '--color-border-strong',
  '--color-ink-4',
  '--color-accent-ink',
  '--color-page',
  '--color-band',
  '--color-surface-sky',
  '--color-surface-warm',
  '--color-surface-plum',
  '--gradient-action',
  '--gradient-ground',
  '--gradient-answer',
  'bg-ground',
  'bg-canvas',
  'border-border',
  'text-ink-4',
  'text-accent-ink',
  'font-titling',
  'font-record',
  'font-measurement',
  'shadow-raised',
  'shadow-floating',
  'shadow-panel',
]

const GUARD_FILE = 'tokens.test.ts'

/** Every file under `src` — a retired name must never come back. */
function sourceFiles(dir: string): string[] {
  const found: string[] = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) found.push(...sourceFiles(full))
    else found.push(full)
  }
  return found
}

describe('the Quiet Room tonal ladder', () => {
  it('declares the three grounds and the record rule', () => {
    expect(resolve('--color-bone')).toBe('#f4efe6')
    expect(resolve('--color-paper')).toBe('#fffcf6')
    expect(resolve('--color-sand')).toBe('#eae2d4')
    expect(resolve('--color-rule')).toBe('#8a806e')
  })

  it('uses one accent and no pure black or white', () => {
    expect(resolve('--color-accent')).toBe('#1e4b38')
    const surfaces = [...declared.keys()].filter((token) => token.startsWith('--color-'))
    for (const token of surfaces) {
      const value = resolve(token)
      if (!/^#[0-9a-f]{6}$/i.test(value)) continue
      expect(value.toLowerCase(), token).not.toBe('#000000')
      expect(value.toLowerCase(), token).not.toBe('#ffffff')
    }
  })

  it.each(FLOORS)('$label clears $floor:1', ({ fg, bg, floor }) => {
    expect(contrast(fg, bg)).toBeGreaterThanOrEqual(floor)
  })

  it('spreads the map ramp enough to read as light', () => {
    // §4.5 pins pine #0b1510 and lit pine #13251b. That ramp measures 7.04 L* — a deliberately
    // short pool of light (§4.8); the old 8 floor was written for the retired, brighter ramp.
    const spread = Math.abs(lightness('--color-map-ground-2') - lightness('--color-map-ground'))
    expect(spread).toBeGreaterThanOrEqual(7)
  })

  it('declares the four gradients and no others', () => {
    const gradients = [...declared.keys()].filter((token) => token.startsWith('--gradient-'))
    expect(gradients.sort()).toEqual([
      '--gradient-first-light',
      '--gradient-map',
      '--gradient-marked',
      '--gradient-morning',
    ])
  })

  it('names the three faces and retires Spectral', () => {
    expect(declared.get('--font-display')).toContain('Fraunces')
    expect(declared.get('--font-ui')).toContain('Archivo')
    expect(declared.get('--font-mono')).toContain('JetBrains Mono')
    expect([...declared.keys()].some((token) => token.startsWith('--font-') && token.includes('spectral'))).toBe(false)
  })

  it('sets the scale with its own line height', () => {
    for (const name of ['hero', 'display', 'title', 'heading', 'body', 'body-sm', 'label', 'micro', 'mono', 'numeral']) {
      expect(declared.has(`--text-${name}`), name).toBe(true)
      expect(declared.has(`--text-${name}--line-height`), name).toBe(true)
    }
  })
})

describe('the retired world', () => {
  it('names no retired token or class anywhere under src', () => {
    const offenders: string[] = []
    for (const file of sourceFiles('src')) {
      if (basename(file) === GUARD_FILE) continue
      const text = readFileSync(file, 'utf8')
      for (const name of RETIRED) {
        if (new RegExp(`(?<![\\w-])${name.replace(/[-/\\^$*+?.()|[\]{}]/g, '\\$&')}(?![\\w-])`).test(text)) {
          offenders.push(`${file}: ${name}`)
        }
      }
    }
    expect(offenders).toEqual([])
  })
})
