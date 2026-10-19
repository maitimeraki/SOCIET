import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { listRunsPage } from '../api/rest'
import type { RunSummary } from '../api/types'
import DashboardView from './dashboardView'
import type { DashboardViewProps } from './dashboardView'
// §13 — the one copy-law guard, shared with every rendered-string test.
import { BANNED_WORD, renderedText } from '../test/copyLaw'

afterEach(() => vi.unstubAllGlobals())

const run = (patch: Partial<RunSummary> = {}): RunSummary => ({
  run_id: 'r1',
  created_at: '2026-10-01T10:00:00Z',
  query: 'Should we expand into Europe?',
  corpus_label: null,
  dataset_id: 'ds-1',
  status: 'complete',
  rounds_executed: 3,
  converged: true,
  verdict_stance: 'POSITIVE',
  ...patch,
})

const render = (props: Partial<DashboardViewProps> = {}) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <DashboardView
        runs={[]}
        loading={false}
        failed={false}
        hasMore={false}
        loadingMore={false}
        onLoadMore={() => {}}
        datasetReady={false}
        {...props}
      />
    </MemoryRouter>,
  )

describe('DashboardPage — the traverse log (plan §3.3)', () => {
  it('renders the six timeline columns from a mocked GET', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [run()], next_cursor: null }))),
    )

    const page = await listRunsPage({ limit: 25 })
    const html = render({ runs: page.items })

    // The same RunTable (§8.4) the /runs section renders — one column set, shared.
    for (const header of ['When', 'Question', 'Corpus', 'Passes', 'Outcome', 'Status']) {
      expect(html).toContain(header)
    }
    // Timestamp cell = `fmtDate(created_at)`, asserted as the exact local-time literal — `TZ` is
    // pinned to UTC in `vite.config.ts`, so this is deterministic and still catches a formatter
    // bug (e.g. an off-by-one day) that comparing against `fmtDate` itself would not (R48 m2).
    expect(html).toContain('1 Oct 2026 10:00')
    expect(html).toContain('Should we expand into Europe?') // question → query
    expect(html).toContain('ds-1') // corpus → dataset_id when the run named no label
    expect(html).toContain('>3<') // passes → rounds_executed
    expect(html).toContain('POSITIVE') // outcome → the stance word beside its symbol
    expect(html).toContain('Complete') // status → StateChip
  })

  it('renders the empty state with the first-run CTA when there are no runs', () => {
    expect(render({ runs: [] })).toContain('Start your first decision')
  })

  it('does not render the empty state while loading or after a failure', () => {
    expect(render({ runs: [], loading: true })).not.toContain('Start your first decision')
    // The rendered apostrophe is entity-escaped by `renderToStaticMarkup`, so assert an unescaped span.
    expect(render({ runs: [], failed: true })).toContain('reach the server')
  })

  it('carries the server message into the failure detail, standing copy when there is none', () => {
    expect(render({ runs: [], failed: true, failDetail: 'API 500: the log is unavailable' })).toContain(
      'API 500: the log is unavailable',
    )
    // No message forwarded → the view's own copy, never an empty detail.
    expect(render({ runs: [], failed: true })).toContain('loads when the server is back')
    // An empty message (a non-Error throw with no text) must fall back too, not render a blank detail.
    expect(render({ runs: [], failed: true, failDetail: '' })).toContain('loads when the server is back')
  })

  it('walks next_cursor on Load more, stopping at the end', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [run()], next_cursor: 'c2' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [run({ run_id: 'r2' })], next_cursor: null })))
    vi.stubGlobal('fetch', fetchMock)

    const first = await listRunsPage({ limit: 25 })
    expect(first.next_cursor).toBe('c2')

    const second = await listRunsPage({ limit: 25, cursor: first.next_cursor })
    expect(second.items.map((entry) => entry.run_id)).toEqual(['r2'])
    expect(second.next_cursor).toBeNull() // the end of the list

    const calls = fetchMock.mock.calls.map((call) => String(call[0]))
    expect(calls[0]).toContain('/api/v1/simulate/debates?limit=25')
    expect(calls[1]).toContain('/api/v1/simulate/debates?limit=25&cursor=c2')
  })

  it('offers Load more only while a cursor remains', () => {
    expect(render({ runs: [run()], hasMore: true })).toContain('Load more')
    expect(render({ runs: [run()], hasMore: false })).not.toContain('Load more')
  })

  it('skips ingest for the primary action once the client holds a corpus', () => {
    expect(render({ datasetReady: true })).toContain('/new/society')
    expect(render({ datasetReady: false })).toContain('/new/ingest')
    expect(render({ datasetReady: false })).not.toContain('/new/society')
  })
})

describe('the copy law (§13) holds on the operate home in every state', () => {
  it('renders no banned word, loaded, empty or failed', () => {
    expect(renderedText(render({ runs: [run()] }))).not.toMatch(BANNED_WORD)
    expect(renderedText(render({ runs: [] }))).not.toMatch(BANNED_WORD)
    expect(renderedText(render({ runs: [], failed: true }))).not.toMatch(BANNED_WORD)
  })
})
