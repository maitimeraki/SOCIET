import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { authMe } from '../api/rest'
import { useAuthStore } from './authStore'

const USER = {
  id: 'u1',
  email: 'a@b.c',
  created_at: '2026-01-01T00:00:00Z',
  role: 'user' as const,
  plan: 'free',
  entitlements: { max_agents: 20, max_rounds: 4, units_remaining: 100, period_end: '2026-12-01T00:00:00Z' },
}

beforeEach(() => useAuthStore.setState({ status: 'unknown', user: null }))
afterEach(() => vi.unstubAllGlobals())

describe('authStore', () => {
  it('setUser marks the session authed; clear drops it back to anon', () => {
    useAuthStore.getState().setUser(USER)
    expect(useAuthStore.getState()).toMatchObject({ status: 'authed', user: USER })

    useAuthStore.getState().clear()
    expect(useAuthStore.getState()).toMatchObject({ status: 'anon', user: null })
  })

  it('a 401 from the transport clears the store through the registered seam', async () => {
    useAuthStore.getState().setUser(USER)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ error: { code: 'unauthorized', message: 'unauthorized', correlation_id: 'c1' } }),
          { status: 401 },
        ),
      ),
    )

    await expect(authMe()).rejects.toThrow()

    expect(useAuthStore.getState().status).toBe('anon')
  })

  it('signin adopts the plan entitlements the server returns', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(USER)))
    vi.stubGlobal('fetch', fetchMock)

    await useAuthStore.getState().signin('a@b.c', 'password1')

    expect(fetchMock.mock.calls[0][0]).toContain('/api/v1/auth/login')
    expect(useAuthStore.getState().user?.entitlements).toEqual(USER.entitlements)
  })

  it('signout clears the store even when the server call fails', async () => {
    useAuthStore.getState().setUser(USER)
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))

    await useAuthStore.getState().signout()

    expect(useAuthStore.getState().status).toBe('anon')
  })
})
