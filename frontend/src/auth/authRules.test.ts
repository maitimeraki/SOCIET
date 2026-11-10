import { describe, expect, it } from 'vitest'
import { nextSuffix } from './authRules'

describe('nextSuffix — the other door’s carried destination', () => {
  it('carries nothing when there is no next', () => {
    expect(nextSuffix(new URLSearchParams())).toBe('')
    expect(nextSuffix(new URLSearchParams('next='))).toBe('')
  })

  it('carries a same-origin path, encoded', () => {
    expect(nextSuffix(new URLSearchParams('next=/runs/abc?tab=verdict'))).toBe(
      '?next=%2Fruns%2Fabc%3Ftab%3Dverdict',
    )
  })

  it('carries only the sanitised path when next points off-site', () => {
    expect(nextSuffix(new URLSearchParams('next=https://evil.example/steal'))).toBe('?next=%2Flanding')
    expect(nextSuffix(new URLSearchParams('next=//evil.example'))).toBe('?next=%2Flanding')
  })
})
