import { describe, expect, it } from 'vitest'
import { fmtDate, fmtElapsed, fmtInt, fmtPct, fmtScore, truncateId } from './format'

describe('format', () => {
  it('formats integers with thousands separators', () => {
    expect(fmtInt(1080)).toBe('1,080')
  })
  it('formats shares as percent', () => {
    expect(fmtPct(0.83)).toBe('83%')
  })
  it('formats scores to two decimals', () => {
    expect(fmtScore(0.7)).toBe('0.70')
  })
  it('formats elapsed seconds as MM:SS', () => {
    expect(fmtElapsed(252)).toBe('04:12')
  })
  it('returns a dash for invalid dates', () => {
    expect(fmtDate('not-a-date')).toBe('—')
  })
  it('truncates long ids', () => {
    expect(truncateId('8f3a41b0c2')).toBe('8f3a…c2')
  })
})
