import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { listRunsPage } from '../api/rest'
import type { RunSummary } from '../api/types'
import { fmtDate } from '../utils/format'
import DashboardView from './dashboardView'
import type { DashboardViewProps } from './dashboardView'

afterEach(() => vi.unstubAllGlobals())

const run = (patch: Partial<RunSummary> = {}): RunSummary => ({
  run_id: 'r1',
  created_at: '2026-10-01T10:00:00Z',
  query: 'Should we expand into Europe?',
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
  it('renders the five timeline columns from a mocked GET', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [run()], next_cursor: null }))),
    )

    const page = await listRunsPage({ limit: 25 })
    const html = render({ runs: page.items })

    for (const header of ['Timestamp', 'Question', 'Documents used', 'Status', 'Agents']) {
      expect(html).toContain(header)
    }
    // Timestamp cell = `fmtDate(created_at)`. Asserted against the same formatter (not a pinned
    // literal) so the check is TZ-stable — Node ignores `TZ` on Windows, so a pinned date would
    // flake on a host outside IST (R48 m2). The shape guard keeps the formatter honest.
    expect(html).toContain(fmtDate(run().created_at))
    expect(fmtDate(run().created_at)).toMatch(/^\d{1,2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}$/)
    expect(html).toContain('Should we expand into Europe?') // question → query
    expect(html).toContain('ds-1') // documents used → dataset_id (the corpus id)
    expect(html).toContain('Complete') // status → StateChip
    expect(html).toContain('—') // agent count — absent from the payload, so an honest dash
  })

  it('renders the empty state with the first-run CTA when there are no runs', () => {
    expect(render({ runs: [] })).toContain('Run your first society')
  })

  it('does not render the empty state while loading or after a failure', () => {
    expect(render({ runs: [], loading: true })).not.toContain('Run your first society')
    // The rendered apostrophe is entity-escaped by `renderToStaticMarkup`, so assert an unescaped span.
    expect(render({ runs: [], failed: true })).toContain('reach the server')
  })

  it('carries the server message into the failure detail, standing copy when there is none', () => {
    expect(render({ runs: [], failed: true, failDetail: 'API 500: the log is unavailable' })).toContain(
      'API 500: the log is unavailable',
    )
    // No message forwarded → the view's own copy, never an empty detail.
    expect(render({ runs: [], failed: true })).toContain('loads when the server is back')
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
