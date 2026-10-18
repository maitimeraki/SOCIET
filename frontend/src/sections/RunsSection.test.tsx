import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { listRunsPage } from '../api/rest'
import type { RunSummary } from '../api/types'
import { filterRuns, RunsView } from './RunsSection'
import type { RunsViewProps } from './RunsSection'

// Moved from `pages/RunsPage.test.tsx` when Task 3.2 repointed `/runs` at `sections/RunsSection.tsx`
// (Ruling F4): the section's behaviour coverage is unchanged, only its home moved with the code.
//
// The suite is node-only (no jsdom) and `useEffect` does not run under `renderToStaticMarkup`, so the
// section is split like `DocumentsSection`: `RunsView` is state-free and prop-driven, asserted here;
// the default export owns the fetch.
afterEach(() => vi.unstubAllGlobals())

const run = (patch: Partial<RunSummary> = {}): RunSummary => ({
  run_id: 'r1',
  created_at: '2026-10-01T10:00:00Z',
  query: 'Should we expand into Europe?',
  corpus_label: 'Europe expansion',
  dataset_id: 'ds-1',
  status: 'complete',
  rounds_executed: 3,
  converged: true,
  verdict_stance: 'POSITIVE',
  ...patch,
})

describe('RunsSection — the v1 paginated shape', () => {
  it('reads { items, next_cursor } and walks the keyset cursor', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [run()], next_cursor: 'cur-2' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [run({ run_id: 'r2' })], next_cursor: null })))
    vi.stubGlobal('fetch', fetchMock)

    const first = await listRunsPage({ limit: 25 })
    expect(first.items.map((entry) => entry.run_id)).toEqual(['r1'])
    expect(first.next_cursor).toBe('cur-2')

    const second = await listRunsPage({ limit: 25, cursor: first.next_cursor })
    expect(second.items.map((entry) => entry.run_id)).toEqual(['r2'])
    expect(second.next_cursor).toBeNull() // the end of the list

    const calls = fetchMock.mock.calls.map((call) => String(call[0]))
    expect(calls[0]).toContain('/api/v1/simulate/debates?limit=25')
    expect(calls[1]).toContain('/api/v1/simulate/debates?limit=25&cursor=cur-2')
  })

  it('surfaces a rejected cursor as an ApiError rather than an empty page', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: { code: 'invalid_cursor', message: 'The pagination cursor is not valid.' } }), {
          status: 400,
        }),
      ),
    )
    await expect(listRunsPage({ cursor: 'forged' })).rejects.toThrowError('The pagination cursor is not valid.')
  })
})

describe('filterRuns', () => {
  const runs = [
    run({ run_id: 'a', status: 'complete', query: 'Expand into Europe' }),
    run({ run_id: 'b', status: 'running', query: 'Hire a CFO' }),
    run({ run_id: 'c', status: 'queued', query: 'Build a plant' }),
    run({ run_id: 'd', status: 'failed', query: 'Expand into Asia' }),
  ]

  it('folds queued into the running filter', () => {
    expect(filterRuns(runs, 'running', '').map((entry) => entry.run_id)).toEqual(['b', 'c'])
  })

  it('filters by question text, case-insensitively', () => {
    expect(filterRuns(runs, 'all', 'expand').map((entry) => entry.run_id)).toEqual(['a', 'd'])
  })

  it('combines both filters', () => {
    expect(filterRuns(runs, 'failed', 'expand').map((entry) => entry.run_id)).toEqual(['d'])
  })

  it('an empty needle keeps every run', () => {
    expect(filterRuns(runs, 'all', '   ')).toHaveLength(4)
  })
})

const render = (props: Partial<RunsViewProps> = {}) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <RunsView runs={[]} loading={false} failed={false} onRetry={() => {}} {...props} />
    </MemoryRouter>,
  )

describe('RunsSection — §8.4 Decisions', () => {
  it('lists the decisions when there are runs, each linking to the run', () => {
    const html = render({ runs: [run()] })
    expect(html).toContain('Should we expand into Europe?')
    expect(html).toContain('href="/runs/r1"')
    expect(html).toContain('Europe expansion') // the corpus, by its label
  })

  it('names the single next action when there are no decisions', () => {
    const html = render({ runs: [] })
    expect(html).toContain('Start a decision')
    expect(html).toContain('/new/ingest')
  })

  it('renders a real error with a retry on failure, never an empty list', () => {
    // The rendered apostrophe is entity-escaped by `renderToStaticMarkup`, so assert an unescaped span.
    const html = render({ runs: [], failed: true })
    expect(html).toContain('reach the server')
    expect(html).toContain('Try again') // the retry affordance
    expect(html).not.toContain('Start a decision') // never the empty state on failure
  })

  it('carries the server message into the failure detail, standing copy when there is none', () => {
    expect(render({ runs: [], failed: true, failDetail: 'API 500: the list is unavailable' })).toContain(
      'API 500: the list is unavailable',
    )
    // No message forwarded → the view's own copy, never an empty detail.
    expect(render({ runs: [], failed: true })).toContain('load when the server is back')
  })

  it('renders skeletons while loading, never the empty state or an empty table', () => {
    const html = render({ runs: [], loading: true })
    expect(html).not.toContain('Start a decision')
    expect(html).not.toContain('<table')
  })
})
