/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

/**
 * §4.8 — the four ramps exist, and they land on their one surface. Node-only: it reads the source
 * files, so a later edit cannot quietly paint a gradient on a sheet. The token inventory itself is
 * guarded by `tokens.test.ts`.
 */

const read = (path: string) => readFileSync(path, 'utf8')
const count = (haystack: string, needle: string) => haystack.split(needle).length - 1

const shell = read('src/components/shell/AppShell.tsx')
const results = read('src/pages/ResultsPage.tsx')

describe('§4.8 the gradient system', () => {
  it('opens the app shell on the morning wash', () => {
    expect(count(shell, 'var(--gradient-morning)')).toBe(1)
  })

  it('paints no gradient on the verdict sheet', () => {
    expect(count(results, 'var(--gradient-')).toBe(0)
  })
})
