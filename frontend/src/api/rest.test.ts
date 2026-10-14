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
})
