import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('apiBase', () => {
  it('is null — and the app still imports — when VITE_API_BASE is unset', async () => {
    vi.stubEnv('VITE_API_BASE', undefined)

    const env = await import('./env')

    expect(env.apiBase).toBeNull()
    expect(env.apiBaseError).toBe('VITE_API_BASE is not configured.')
  })

  it('treats the empty string as configured, because dev is same-origin through the proxy', async () => {
    vi.stubEnv('VITE_API_BASE', '')

    const env = await import('./env')

    expect(env.apiBase).toBe('')
    expect(env.apiBaseError).toBeNull()
  })

  it('strips a trailing slash from a configured base', async () => {
    vi.stubEnv('VITE_API_BASE', 'https://api.example.com/')

    expect((await import('./env')).apiBase).toBe('https://api.example.com')
  })
})

describe('rest client under a missing VITE_API_BASE', () => {
  it('fails recoverably from request() instead of throwing at import time', async () => {
    vi.stubEnv('VITE_API_BASE', undefined)
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const rest = await import('../api/rest')

    const error = await rest.health().catch((e: unknown) => e)
    expect(error).toBeInstanceOf(rest.ConfigError)
    expect((error as Error).name).toBe('ConfigError')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('sends a same-origin request when the empty string is configured', async () => {
    vi.stubEnv('VITE_API_BASE', '')
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ status: 'healthy', version: '1', active_jobs: 0 })))
    vi.stubGlobal('fetch', fetchMock)

    await (await import('../api/rest')).health()

    expect(fetchMock.mock.calls[0][0]).toBe('/health')
  })
})
