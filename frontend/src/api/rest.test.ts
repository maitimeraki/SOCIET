import { describe, expect, it, vi, afterEach } from 'vitest'
import { NetworkError, health, ingestFiles } from './rest'

afterEach(() => {
  vi.unstubAllGlobals()
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
})
