/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

/**
 * §15.1.3 — the two new ramps exist, exactly as specified, and each is painted on its one surface.
 * Node-only: it reads the source files, so a later Tailwind/JSX edit cannot quietly drop the token
 * or move it onto a card.
 */

const read = (path: string) => readFileSync(path, 'utf8')
const count = (haystack: string, needle: string) => haystack.split(needle).length - 1

const css = read('src/index.css')
const shell = read('src/components/shell/AppShell.tsx')
const results = read('src/pages/ResultsPage.tsx')

describe('§15.1.3 the two new gradient ramps', () => {
  it('declares both exact ramps in index.css', () => {
    expect(css).toContain('--gradient-ground: linear-gradient(180deg, #F4F6FA 0%, #ECEFF4 320px);')
    expect(css).toContain('--gradient-answer: linear-gradient(180deg, #ECDFF2 0%, #E5D4EC 100%);')
  })

  it('paints the ground on the main region, never the rail or a record', () => {
    expect(count(shell, 'var(--gradient-ground)')).toBe(1)
    expect(count(results, 'var(--gradient-ground)')).toBe(0)
  })

  it('paints the answer band on the Verdict page only', () => {
    expect(count(results, 'var(--gradient-answer)')).toBe(1)
    expect(count(shell, 'var(--gradient-answer)')).toBe(0)
  })
})
