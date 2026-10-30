import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

// No jsdom: the effect-driven states cannot be reached under SSR, so the connection copy is
// pinned by reading the source — the same node-only guard `src/test/gradients.test.ts` uses.
const source = readFileSync('src/components/shell/HealthDot.tsx', 'utf8')

describe('the connection reading speaks the customer’s words (§7.3)', () => {
  it('says Connected when the service answers, and Working otherwise', () => {
    expect(source).toContain("'Connected'")
    expect(source).toContain("'Working'")
    expect(source).toContain("'Checking…'")
  })

  it('never shows server or API jargon', () => {
    expect(source).not.toContain('API online')
    expect(source).not.toContain('API unreachable')
    expect(source).not.toContain('uvicorn')
  })
})
