import { describe, expect, it } from 'vitest'
import { fmtBytes, fmtDate, fmtElapsed, fmtInt, fmtPct, fmtScore, truncateId } from './format'

describe('format', () => {
  it('formats integers with thousands separators', () => {
    expect(fmtInt(1080)).toBe('1,080')
  })
  it('formats a material figure in bytes, KB, MB, then GB', () => {
    expect(fmtBytes(512)).toBe('512 B')
    expect(fmtBytes(20_480)).toBe('20 KB')
    expect(fmtBytes(840_000)).toBe('840 KB')
    expect(fmtBytes(620_000_000)).toBe('620 MB')
    expect(fmtBytes(2_400_000)).toBe('2 MB')
    expect(fmtBytes(2_000_000_000)).toBe('2 GB')
    expect(fmtBytes(2_500_000_000)).toBe('2.5 GB')
    expect(fmtBytes(12_000_000_000)).toBe('12 GB')
  })
  it('promotes a unit that rounds to 1000 instead of printing 1000', () => {
    expect(fmtBytes(999)).toBe('999 B')
    expect(fmtBytes(1_000)).toBe('1 KB')
    expect(fmtBytes(999_999)).toBe('1 MB')
    expect(fmtBytes(1_000_000)).toBe('1 MB')
    expect(fmtBytes(999_999_999)).toBe('1 GB')
    expect(fmtBytes(1_000_000_000)).toBe('1 GB')
    expect(fmtBytes(9_999_999_999)).toBe('10 GB')
    expect(fmtBytes(10_000_000_000)).toBe('10 GB')
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
