import { describe, expect, it, vi, afterEach } from 'vitest'
import { NetworkError, health, ingestFiles } from './rest'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.resetModules()
})

describe('rest client', () => {
  it('parses a JSON body on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'healthy', version: '1.0', active_jobs: 2 }))))
    const result = await health()
    expect(result.active_jobs).toBe(2)
  })

  it('throws ApiError carrying the server detail', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Unsupported file type (.xlsx)' }), { status: 415 })))
    await expect(ingestFiles([new File(['x'], 'a.xlsx')])).rejects.toThrowError('Unsupported file type (.xlsx)')
  })

  it('throws NetworkError when fetch rejects', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('fetch failed')))
    await expect(health()).rejects.toBeInstanceOf(NetworkError)
  })

  it('sends files as multipart form data', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ documents: [], failures: [] })))
    vi.stubGlobal('fetch', fetchMock)
    await ingestFiles([new File(['hello'], 'notes.txt')])
    const body = fetchMock.mock.calls[0][1].body as FormData
    expect((body.get('files') as File).name).toBe('notes.txt')
  })

  it('short-circuits with a recoverable ConfigError when VITE_API_BASE is unset', async () => {
    vi.stubEnv('VITE_API_BASE', undefined)
    vi.resetModules()
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const rest = await import('./rest')

    await expect(rest.health()).rejects.toBeInstanceOf(rest.ConfigError)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('sends cookies on every request (credentials: include)', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ status: 'healthy', version: '1', active_jobs: 0 })))
    vi.stubGlobal('fetch', fetchMock)

    await health()

    expect(fetchMock.mock.calls[0][1].credentials).toBe('include')
  })

  it('invokes the unauthorized handler on a 401 and does not retry', async () => {
    vi.resetModules()
    const rest = await import('./rest')
    const onUnauthorized = vi.fn()
    rest.registerUnauthorizedHandler(onUnauthorized)
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: 'unauthorized' }), { status: 401 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(rest.authMe()).rejects.toBeInstanceOf(rest.ApiError)

    expect(onUnauthorized).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledTimes(1) // no retry
  })

  it('does not invoke the unauthorized handler on a non-401 error', async () => {
    vi.resetModules()
    const rest = await import('./rest')
    const onUnauthorized = vi.fn()
    rest.registerUnauthorizedHandler(onUnauthorized)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'boom' }), { status: 500 })),
    )

    await expect(rest.authMe()).rejects.toBeInstanceOf(rest.ApiError)

    expect(onUnauthorized).not.toHaveBeenCalled()
  })
})

describe('CSRF double-submit header (R36)', () => {
  const csrfHeader = (fetchMock: ReturnType<typeof vi.fn>) =>
    (fetchMock.mock.calls[0][1].headers as Headers).get('X-CSRF-Token')

  it('emits X-CSRF-Token on a state-changing request when the csrf cookie is present', async () => {
    vi.stubGlobal('document', { cookie: 'theme=dark; csrf=tok-123' })
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ documents: [], failures: [] })))
    vi.stubGlobal('fetch', fetchMock)

    await ingestFiles([new File(['x'], 'a.txt')])

    expect(csrfHeader(fetchMock)).toBe('tok-123')
  })

  it('omits the header when the csrf cookie is absent (and never throws without document)', async () => {
    // No `document` stub: the node-env suite has none, and the read must stay defensive.
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ documents: [], failures: [] })))
    vi.stubGlobal('fetch', fetchMock)

    await ingestFiles([new File(['x'], 'a.txt')])

    expect(csrfHeader(fetchMock)).toBeNull()
  })

  it('never emits the header on a GET, even with the cookie present', async () => {
    vi.stubGlobal('document', { cookie: 'csrf=tok-123' })
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ status: 'healthy', version: '1', active_jobs: 0 })))
    vi.stubGlobal('fetch', fetchMock)

    await health()

    expect(csrfHeader(fetchMock)).toBeNull()
  })
})
