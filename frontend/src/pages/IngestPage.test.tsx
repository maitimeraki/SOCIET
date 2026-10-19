import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { runFileIngest, runUrlIngest } from '../api/ingestFlow'
import DocCard from '../components/ingest/DocCard'
import { BANNED_WORD, renderedText } from '../test/copyLaw'
import type { DraftDoc } from '../wizard/draftStore'
import IngestPage from './IngestPage'

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
    expect(outcome).toEqual({ kind: 'failed', reason: 'the extraction returned no sections' })
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

// The phone layout: at 390 px the field and the build button used to sit in one row and the button
// overlapped the field. They stack below `sm`; the row only returns at `sm` and up.
describe('the corpus form stacks on a phone', () => {
  it('stacks the field and the button below sm, and spreads them only at sm and up', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <IngestPage />
      </MemoryRouter>,
    )

    // Stacked below sm; the row only returns at sm and up. The unqualified row classes are gone —
    // that is the 390 px collision.
    expect(html).toContain('class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between sm:gap-6"')
    expect(html).not.toContain('class="flex items-end justify-between gap-6"')
    // The button fills the column on a phone and goes back to its own width at sm.
    expect(html).toContain('w-full sm:w-auto')
  })
})

// §13(copy law): the failure reason reaches the customer verbatim — IngestPage renders it as
// `Extraction failed: {reason}` and DocCard renders it as `Failed — {doc.error}`. Both must be free
// of the banned vocabulary (a "job" leaked here before the fix).
describe('the ingest failure speaks the customer’s language (§13)', () => {
  const failure = async (jobOverrides: Record<string, unknown>) => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(ACCEPTED, { status: 202 }))
      .mockResolvedValueOnce(json({ ...DONE, result: null, ...jobOverrides }))
    vi.stubGlobal('fetch', fetchMock)
    const outcome = await runFileIngest([new File(['x'], 'a.pdf')])
    if (outcome.kind !== 'failed') throw new Error(`expected a failure, got ${outcome.kind}`)
    return outcome.reason
  }

  const docCardWith = (reason: string) => {
    const doc: DraftDoc = {
      document_id: 'd1',
      title: 'a.pdf',
      text: '',
      word_count: 0,
      source_type: 'file',
      status: 'failed',
      error: reason,
    }
    return renderToStaticMarkup(<DocCard doc={doc} onRemove={() => {}} onRetry={() => {}} />)
  }

  it('the stall reason is clean, and clean once DocCard renders it', async () => {
    const reason = await failure({ status: 'failed' })
    expect(reason).not.toMatch(BANNED_WORD)
    expect(renderedText(docCardWith(reason))).not.toMatch(BANNED_WORD)
  })

  it('the no-sections reason is clean, and clean once DocCard renders it', async () => {
    const reason = await failure({ status: 'completed', result: {} })
    expect(reason).not.toMatch(BANNED_WORD)
    expect(renderedText(docCardWith(reason))).not.toMatch(BANNED_WORD)
  })
})
