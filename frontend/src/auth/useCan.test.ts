import { describe, expect, it } from 'vitest'
import type { Role, User } from '../api/types'
import { can } from './useCan'

const user = (role: Role): User => ({
  id: 'u1',
  email: 'a@b.c',
  created_at: '2026-01-01T00:00:00Z',
  role,
  plan: 'free',
  entitlements: {
    max_agents: 10,
    max_rounds: 3,
    units_remaining: 12,
    period_end: '2026-12-01T00:00:00Z',
  },
})

describe('can — the role truth table', () => {
  it('denies when there is no user', () => {
    expect(can(null, 'admin')).toBe(false)
  })

  it('denies a role the user does not hold', () => {
    expect(can(user('user'), 'admin')).toBe(false)
    expect(can(user('support'), 'admin')).toBe(false)
  })

  it('allows the role the user holds', () => {
    expect(can(user('admin'), 'admin')).toBe(true)
    expect(can(user('support'), 'support')).toBe(true)
  })

  it('allows when any listed role matches', () => {
    expect(can(user('admin'), 'support', 'admin')).toBe(true)
  })

  it('denies when no role is asked for', () => {
    expect(can(user('admin'))).toBe(false)
  })
})
