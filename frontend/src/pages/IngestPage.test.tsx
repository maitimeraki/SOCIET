import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { runFileIngest, runUrlIngest } from '../api/ingestFlow'

// vitest runs in the node environment; poll.ts sleeps via window.setTimeout.
beforeEach(() => {
  vi.stubGlobal('window', { setTimeout })
})
afterEach(() => {
  vi.unstubAllGlobals()
})

const json = (body: unknown, init?: ResponseInit) => new Response(JSON.stringify(body), init)

const ACCEPTED = { job_id: 'job-1', status: 'queued' }
const DONE = {
  job_id: 'job-1',
  mode: 'extract_upload',
  status: 'completed',
  stage: 'completed',
  progress: 1,
  // R17/9c: the upload ids are NESTED under `result`, not a flat envelope.
  result: { upload_ids: ['u1', 'u2'] },
}
const DOCUMENTS = {
  documents: [
    { upload_id: 'u1', document_id: 'd1', title: 'notes.txt', text: 'hello', word_count: 1, source_type: 'file' },
    { upload_id: 'u2', document_id: 'd2', title: 'brief.md', text: 'world', word_count: 1, source_type: 'file' },
  ],
}

const paths = (fetchMock: ReturnType<typeof vi.fn>) => fetchMock.mock.calls.map((call) => String(call[0]))

describe('the R17 ingest transport (202 → poll → documents)', () => {
  it('posts the batch, polls the job, then reads the extracted documents by the nested upload ids', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(ACCEPTED, { status: 202 }))
      .mockResolvedValueOnce(json(DONE))
      .mockResolvedValueOnce(json(DOCUMENTS))
    vi.stubGlobal('fetch', fetchMock)

    const outcome = await runFileIngest([new File(['hello'], 'notes.txt')])

    expect(outcome).toEqual({ kind: 'documents', documents: DOCUMENTS.documents })
    expect(paths(fetchMock)[0]).toContain('/api/v1/ingest/files')
    expect(paths(fetchMock)[1]).toContain('/api/v1/jobs/job-1')
    expect(paths(fetchMock)[2]).toContain('/api/v1/ingest/documents?upload_ids=u1%2Cu2')
  })

  it('a failed job is a readable failure, not a silent stall', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(ACCEPTED, { status: 202 }))
      .mockResolvedValueOnce(json({ ...DONE, status: 'failed', error: 'corrupt PDF' }))
    vi.stubGlobal('fetch', fetchMock)

    expect(await runFileIngest([new File(['x'], 'a.pdf')])).toEqual({ kind: 'failed', reason: 'corrupt PDF' })
  })

  it('a cancelled job reads as cancelled (a terminal status, not an endless poll)', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(ACCEPTED, { status: 202 }))
      .mockResolvedValueOnce(json({ ...DONE, status: 'cancelled', result: null }))
    vi.stubGlobal('fetch', fetchMock)

    expect(await runFileIngest([new File(['x'], 'a.txt')])).toEqual({
      kind: 'failed',
      reason: 'the extraction was cancelled',
    })
  })

  it('a completed job with no upload ids fails honestly rather than fetching a bare documents call', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(ACCEPTED, { status: 202 }))
      .mockResolvedValueOnce(json({ ...DONE, result: {} }))
    vi.stubGlobal('fetch', fetchMock)

    const outcome = await runFileIngest([new File(['x'], 'a.txt')])
    expect(outcome).toEqual({ kind: 'failed', reason: 'the extraction job returned no upload ids' })
    expect(paths(fetchMock)).toHaveLength(2)
  })

  it('a 429 is its own quota state with the Retry-After, not a generic failure', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      json(
        { detail: { code: 'quota_exceeded', message: 'Upload quota exceeded for this month.' } },
        { status: 429, headers: { 'Retry-After': '3600' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    expect(await runUrlIngest('https://example.com')).toEqual({
      kind: 'quota',
      message: 'Upload quota exceeded for this month.',
      retryAfterSeconds: 3600,
    })
  })

  it('a URL fetch follows the same 202 → poll → documents path', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(ACCEPTED, { status: 202 }))
      .mockResolvedValueOnce(json({ ...DONE, result: { upload_ids: ['u1'] } }))
      .mockResolvedValueOnce(json({ documents: [DOCUMENTS.documents[0]] }))
    vi.stubGlobal('fetch', fetchMock)

    const outcome = await runUrlIngest('https://example.com/report')
    expect(outcome.kind).toBe('documents')
    expect(paths(fetchMock)[0]).toContain('/api/v1/ingest/url')
  })
})
