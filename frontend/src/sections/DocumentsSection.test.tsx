import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { listUploads } from '../api/rest'
import type { UploadRow } from '../api/types'
import { DocumentsView } from './DocumentsSection'
import type { DocumentsViewProps } from './DocumentsSection'
// §13 — the one copy-law guard, shared with every rendered-string test.
import { BANNED_WORD, renderedText } from '../test/copyLaw'

// The suite is node-only (no jsdom) and `useEffect` does not run under `renderToStaticMarkup`, so the
// section is split like the dashboard: `DocumentsView` is state-free and prop-driven, asserted here;
// the default export owns the fetch. The list/empty/error states are the section's whole surface.
afterEach(() => vi.unstubAllGlobals())

const doc = (patch: Partial<UploadRow> = {}): UploadRow => ({
  id: 'u1',
  name: 'market-research.pdf',
  bytes: 20480,
  mime: 'application/pdf',
  read: true,
  dataset_id: 'ds-1',
  dataset_name: 'Europe expansion',
  created_at: '2026-10-01T10:00:00Z',
  ...patch,
})

const render = (props: Partial<DocumentsViewProps> = {}) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <DocumentsView documents={[]} loading={false} failed={false} onRetry={() => {}} {...props} />
    </MemoryRouter>,
  )

describe('DocumentsSection — §8.3 Documents', () => {
  it('renders each document with when it was added and what came from it', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [doc()] })))
    vi.stubGlobal('fetch', fetchMock)

    const { items } = await listUploads()
    const html = render({ documents: items })

    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/v1/uploads')
    expect(html).toContain('market-research.pdf') // the document's name
    // `created_at` → `fmtDate`, asserted as the exact local-time literal (`TZ` pinned to UTC in
    // vite.config.ts) — a formatter bug is caught, not just a comparison against `fmtDate` itself.
    expect(html).toContain('1 Oct 2026 10:00') // when it was added
    expect(html).toContain('Read') // what came from it — its text was extracted
    expect(html).toContain('Europe expansion') // the corpus it joined
  })

  it('names the single next action when there are no documents', () => {
    const html = render({ documents: [] })
    expect(html).toContain('Upload documents')
    expect(html).toContain('/new/ingest')
  })

  it('renders a real error with a retry on failure, never an empty list', () => {
    // The rendered apostrophe is entity-escaped by `renderToStaticMarkup`, so assert an unescaped span.
    const html = render({ documents: [], failed: true })
    expect(html).toContain('reach the server')
    expect(html).toContain('Try again') // the retry affordance
    expect(html).not.toContain('Upload documents') // never the empty state on failure
  })

  it('carries the server message into the failure detail, standing copy when there is none', () => {
    expect(render({ documents: [], failed: true, failDetail: 'API 500: the list is unavailable' })).toContain(
      'API 500: the list is unavailable',
    )
    // No message forwarded → the view's own copy, never an empty detail.
    expect(render({ documents: [], failed: true })).toContain('load when the server is back')
  })
})

describe('the copy law (§13) holds on Documents when loaded, empty or failed', () => {
  it('renders no banned word in any state', () => {
    expect(renderedText(render({ documents: [doc()] }))).not.toMatch(BANNED_WORD)
    expect(renderedText(render({ documents: [] }))).not.toMatch(BANNED_WORD)
    expect(renderedText(render({ documents: [], failed: true }))).not.toMatch(BANNED_WORD)
  })
})
