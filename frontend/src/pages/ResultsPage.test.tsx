import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { DEBATE_CONFIG_DEFAULTS, type RunDoc, type RunSummary } from '../api/types'
import { reportFromState } from '../components/run/reportFromState'
import { applyStoredResult, fold } from '../run/reducer'
import { RUN_SAMPLE } from '../run/__fixtures__/run-sample'
import { BANNED_TERMS, renderedText } from '../test/copyLaw'
import { VerdictsPageView, loadVerdicts, type VerdictsPageViewProps } from './ResultsPage'

const report = reportFromState(fold(RUN_SAMPLE, () => 0))!

const render = (props: Partial<VerdictsPageViewProps> = {}) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <VerdictsPageView
        latest={null}
        earlier={[]}
        loading={false}
        failed={false}
        onRetry={() => {}}
        onRestored={() => Promise.resolve()}
        {...props}
      />
    </MemoryRouter>,
  )

const filled = {
  latest: { runId: 'r1', report },
  earlier: [{ runId: 'r0', question: 'Should we hire?', stance: 'POSITIVE' as const, share: 0.74, date: '2026-09-01T10:00:00Z' }],
}

describe('VerdictsPageView', () => {
  it('renders the latest answer as the report as given, and every earlier verdict as a ruled row', () => {
    const html = render(filled)
    expect(html).toContain('Expand, cautiously, into one market first.')
    expect(html).toContain('Should we hire?')
    expect(html).toContain('0.74')
    expect(html).toContain('/runs/r0')
    expect(html).toContain('1 Sept 2026')
    expect(html).toContain('Positive')
  })

  it('offers the retry for a latest report that was not produced', () => {
    const unproduced = reportFromState(applyStoredResult(fold([], () => 0), { status: 'not_produced' }))!
    const html = render({ latest: { runId: 'r1', report: unproduced }, earlier: [] })
    expect(html).toContain('Report not produced')
    expect(html).toContain('Retry report')
  })

  it('offers one print action for a produced report, and none for a report not produced', () => {
    expect(render(filled)).toContain('Export document')
    const unproduced = reportFromState(applyStoredResult(fold([], () => 0), { status: 'not_produced' }))!
    expect(render({ latest: { runId: 'r1', report: unproduced }, earlier: [] })).not.toContain('Export document')
  })

  it('renders the empty state and the failure state', () => {
    expect(render({ latest: null, earlier: [] })).toContain('Your first answer appears here')
    const failed = render({ latest: null, earlier: [], failed: true })
    expect(failed).toContain('reach the server')
    expect(failed).toContain('Try again')
  })

  it('carries no banned word', () => {
    expect(renderedText(render())).not.toMatch(BANNED_TERMS)
    expect(renderedText(render(filled))).not.toMatch(BANNED_TERMS)
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('loadVerdicts', () => {
  const run = (patch: Partial<RunSummary>): RunSummary => ({
    run_id: 'r',
    created_at: '2026-10-09T10:00:00Z',
    query: 'Should we expand?',
    corpus_label: null,
    dataset_id: 'd1',
    status: 'complete',
    rounds_executed: 2,
    converged: true,
    verdict_stance: 'POSITIVE',
    verdict_confidence: null,
    ...patch,
  })
  const good: RunDoc = {
    run_id: 'r-good',
    created_at: '2026-10-09T10:00:00Z',
    query: 'Should we expand?',
    dataset_id: 'd1',
    config: DEBATE_CONFIG_DEFAULTS,
    status: 'complete',
    events: RUN_SAMPLE,
  }
  const reply = (body: unknown, ok = true, status = 200) => ({
    ok,
    status,
    statusText: ok ? 'OK' : 'Not Found',
    headers: { get: () => null },
    json: async () => body,
  })

  it('opens the first readable answer and builds the rest of the archive from the list', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/r-bad')) return reply({ error: { code: 'not_found', message: 'not found', correlation_id: 'c1' } }, false, 404)
        if (url.includes('/r-good')) return reply(good)
        return reply({
          items: [
            run({ run_id: 'r-bad', query: 'A run whose record is gone', verdict_confidence: 0.61 }),
            run({ run_id: 'r-good', verdict_confidence: 0.82 }),
          ],
          next_cursor: null,
        })
      }),
    )
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const loaded = await loadVerdicts()

    expect(loaded.latest?.runId).toBe('r-good')
    expect(loaded.latest?.report.title).toBe('Should we expand into the European market in 2027?')
    expect(loaded.earlier).toEqual([
      {
        runId: 'r-bad',
        question: 'A run whose record is gone',
        stance: 'POSITIVE',
        share: 0.61,
        date: '2026-10-09T10:00:00Z',
      },
    ])
    expect(errorSpy).toHaveBeenCalled()
  })

  it('opens a retried report from the stored result, over the event log it was filed with', async () => {
    const retried: RunDoc = {
      ...good,
      run_id: 'r-retried',
      events: [{ type: 'complete', converged: false, title: null, markdown: null, status: 'not_produced', final_stances: {}, warnings: [], rounds_executed: 0 }],
      result: { status: 'produced', title: 'Expand?', markdown: '# Expand?\n## Recommendation\nExpand.', sources: {}, final_stances: {} },
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/r-retried')) return reply(retried)
        return reply({ items: [run({ run_id: 'r-retried' })], next_cursor: null })
      }),
    )

    const loaded = await loadVerdicts()

    expect(loaded.latest?.runId).toBe('r-retried')
    expect(loaded.latest?.report.markdown).toContain('## Recommendation')
  })

  it('does not headline a run whose report was not produced while a produced one exists', async () => {
    const legacy: RunDoc = {
      ...good,
      run_id: 'r-legacy',
      events: [{ type: 'complete', converged: false, final_stances: {}, warnings: [], rounds_executed: 0 }],
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/r-legacy')) return reply(legacy)
        if (url.includes('/r-good')) return reply(good)
        return reply({
          items: [run({ run_id: 'r-legacy', verdict_confidence: 0.4 }), run({ run_id: 'r-good', verdict_confidence: 0.82 })],
          next_cursor: null,
        })
      }),
    )

    const loaded = await loadVerdicts()

    expect(loaded.latest?.runId).toBe('r-good')
    expect(loaded.earlier.map((row) => row.runId)).toEqual(['r-legacy'])
  })

  it('headlines a run whose report was not produced only when no produced one exists', async () => {
    const legacy: RunDoc = {
      ...good,
      run_id: 'r-legacy',
      events: [{ type: 'complete', converged: false, final_stances: {}, warnings: [], rounds_executed: 0 }],
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/r-legacy')) return reply(legacy)
        return reply({ items: [run({ run_id: 'r-legacy', verdict_confidence: 0.4 })], next_cursor: null })
      }),
    )

    const loaded = await loadVerdicts()

    expect(loaded.latest?.runId).toBe('r-legacy')
    expect(loaded.latest?.report.reportStatus).toBe('not_produced')
  })

  it('reads at most five documents to find the headline, however long the archive', async () => {
    const legacy = (id: string): RunDoc => ({
      ...good,
      run_id: id,
      events: [{ type: 'complete', converged: false, final_stances: {}, warnings: [], rounds_executed: 0 }],
    })
    const ids = Array.from({ length: 8 }, (_, index) => `r-legacy-${index}`)
    const documentReads: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        const match = url.match(/\/debates\/(r-legacy-\d+)$/)
        if (match) {
          documentReads.push(match[1])
          return reply(legacy(match[1]))
        }
        return reply({ items: ids.map((id) => run({ run_id: id })), next_cursor: null })
      }),
    )

    const loaded = await loadVerdicts()

    expect(documentReads).toHaveLength(5)
    expect(loaded.latest?.runId).toBe('r-legacy-0')
    expect(loaded.earlier.map((row) => row.runId)).toEqual(ids.slice(1))
  })

  it('stops reading at the first produced report it finds', async () => {
    const legacy = (id: string): RunDoc => ({
      ...good,
      run_id: id,
      events: [{ type: 'complete', converged: false, final_stances: {}, warnings: [], rounds_executed: 0 }],
    })
    const documents: Record<string, RunDoc> = {
      'r-a': legacy('r-a'),
      'r-b': { ...good, run_id: 'r-b' },
      'r-c': legacy('r-c'),
    }
    const documentReads: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        const match = url.match(/\/debates\/(r-[a-z])$/)
        if (match) {
          documentReads.push(match[1])
          return reply(documents[match[1]])
        }
        return reply({ items: [run({ run_id: 'r-a' }), run({ run_id: 'r-b' }), run({ run_id: 'r-c' })], next_cursor: null })
      }),
    )

    const loaded = await loadVerdicts()

    expect(documentReads).toEqual(['r-a', 'r-b'])
    expect(loaded.latest?.runId).toBe('r-b')
  })

  it('leaves every answered row in the archive when no document can be read', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/debates/')) return reply({ error: { code: 'not_found', message: 'not found', correlation_id: 'c1' } }, false, 404)
        return reply({
          items: [
            run({ run_id: 'r-bad', verdict_confidence: 0.61 }),
            run({ run_id: 'r-gone', query: 'Also gone', verdict_confidence: 0.55 }),
          ],
          next_cursor: null,
        })
      }),
    )
    vi.spyOn(console, 'error').mockImplementation(() => {})

    const loaded = await loadVerdicts()

    expect(loaded.latest).toBeNull()
    expect(loaded.earlier).toEqual([
      { runId: 'r-bad', question: 'Should we expand?', stance: 'POSITIVE', share: 0.61, date: '2026-10-09T10:00:00Z' },
      { runId: 'r-gone', question: 'Also gone', stance: 'POSITIVE', share: 0.55, date: '2026-10-09T10:00:00Z' },
    ])
  })
})
