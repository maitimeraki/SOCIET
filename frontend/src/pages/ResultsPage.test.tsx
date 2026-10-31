import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { DEBATE_CONFIG_DEFAULTS, type RunDoc, type RunSummary } from '../api/types'
import { NARRATIVE_FALLBACK_COPY } from '../components/verdict/NarrativeFallbackNotice'
import { reportFromState } from '../components/run/reportFromState'
import { fold } from '../run/reducer'
import { verdictView } from '../run/selectors'
import { RUN_SAMPLE } from '../run/__fixtures__/run-sample'
import { BANNED_TERMS, renderedText } from '../test/copyLaw'
import { VerdictsPageView, loadVerdicts, type VerdictsPageViewProps } from './ResultsPage'

const FILED_AT = '2026-10-09T10:00:00Z'
const STATE = fold(RUN_SAMPLE)
const view = verdictView(STATE)
const report = reportFromState(STATE, FILED_AT)!

const render = (props: Partial<VerdictsPageViewProps> = {}) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <VerdictsPageView
        latest={null}
        earlier={[]}
        loading={false}
        failed={false}
        onRetry={() => {}}
        {...props}
      />
    </MemoryRouter>,
  )

const filled = {
  latest: { runId: 'r1', report, narrativeStatus: view!.narrativeStatus },
  earlier: [{ runId: 'r0', question: 'Should we hire?', stance: 'POSITIVE' as const, share: 0.74, date: '2026-09-01T10:00:00Z' }],
}

describe('VerdictsPageView', () => {
  it('renders the latest answer as the verdict sheet and every earlier verdict as a ruled row', () => {
    const html = render(filled)
    expect(html).toContain('Should we expand into the European market in 2027?')
    expect(html).toContain('Should we hire?')
    expect(html).toContain('0.74')
    expect(html).toContain('/runs/r0')
    // Position, share and date lead, before any prose (§7.6).
    expect(html).toContain('Export document')
    expect(html).toContain('9 Oct 2026')
    expect(html).toContain('weighted share')
    expect(html).toContain('0.83')
    expect(html).toContain('The case against')
    expect(html).toContain('Entry cost outweighs the single market.')
    // The source row keeps its real provenance breadcrumb (R62) instead of a dangling dash.
    expect(html).toContain('Section 3')
    // The earlier row carries its own date, position and share.
    expect(html).toContain('1 Sept 2026')
    expect(html).toContain('Positive')
  })

  it('shows the narrative fallback notice, and does not print the fallback summary twice', () => {
    const verdict = STATE.verdict!
    const summary = verdict.summary
    const fallback = reportFromState(
      { ...STATE, verdict: { ...verdict, narrative: summary, narrativeStatus: 'fallback' } },
      FILED_AT,
    )!
    const html = render({ latest: { runId: 'r1', report: fallback, narrativeStatus: 'fallback' }, earlier: [] })
    expect(html).toContain(NARRATIVE_FALLBACK_COPY)
    expect(html.split(summary)).toHaveLength(2)
  })

  it('isolates the sheet for printing — chrome and the archive stay off the page', () => {
    const html = render(filled)
    expect(html).toContain('print:hidden')
    expect(html).toContain('print:block')
  })

  it('derives who held which view in STANCE_ORDER and drops the empty groups', () => {
    const html = render(filled)
    expect(html).toContain('D. Weber, P. Silva')
    expect(html).toContain('M. Chen')
    expect(html.indexOf('D. Weber')).toBeLessThan(html.indexOf('M. Chen'))
    // L. Novak is on the roster but holds no final stance — the sheet invents no row.
    expect(html).not.toContain('L. Novak')
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
        if (url.includes('/r-bad')) return reply({ detail: 'not found' }, false, 404)
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
    expect(loaded.latest?.report.filed).toBe('9 Oct 2026')
    expect(loaded.latest?.report.sources).toEqual([{ document: 'eu-market-2027.pdf', reference: 'Section 3' }])
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

  it('leaves every answered row in the archive when no document can be read', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/debates/')) return reply({ detail: 'not found' }, false, 404)
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
