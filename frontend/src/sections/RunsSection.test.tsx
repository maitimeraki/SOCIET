import { afterEach, describe, expect, it, vi } from 'vitest'
import { listRunsPage } from '../api/rest'
import type { RunSummary } from '../api/types'
import { filterRuns } from './RunsSection'

// Moved from `pages/RunsPage.test.tsx` when Task 3.2 repointed `/runs` at `sections/RunsSection.tsx`
// (Ruling F4): the section's behaviour coverage is unchanged, only its home moved with the code.
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
