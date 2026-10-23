import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import ruleClasses, { ruleClasses as named } from './Rule'

describe('Rule — the record vocabulary', () => {
  it('names every side it can draw', () => {
    expect(ruleClasses('top')).toBe('rule-t')
    expect(ruleClasses('bottom')).toBe('rule-b')
    expect(ruleClasses('both')).toBe('rule-y')
    expect(ruleClasses('around')).toBe('divide-rule')
  })

  it('draws the two vertical sides, so a column hairline is the same hairline', () => {
    expect(ruleClasses('left')).toBe('rule-l')
    expect(ruleClasses('right')).toBe('rule-r')
  })

  it('defaults to the top side', () => {
    expect(ruleClasses()).toBe('rule-t')
  })

  it('takes the dark tone for the map’s own hairline', () => {
    expect(ruleClasses('top', 'dark')).toContain('rule-t')
    expect(ruleClasses('top', 'dark')).toContain('rule-dark')
    expect(ruleClasses('top', 'light')).not.toContain('rule-dark')
  })

  it('exports the vocabulary itself as the default, so every kit file has one', () => {
    expect(named).toBe(ruleClasses)
  })
})
