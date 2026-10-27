import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { DEBATE_CONFIG_DEFAULTS, type RunDoc, type RunSummary } from '../api/types'
import { fold } from '../run/reducer'
import { verdictView } from '../run/selectors'
import { RUN_SAMPLE } from '../run/__fixtures__/run-sample'
import { BANNED_WORD, renderedText } from '../test/copyLaw'
import { VerdictsPageView, loadVerdicts, type VerdictsPageViewProps } from './ResultsPage'

const view = verdictView(fold(RUN_SAMPLE))

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

describe('VerdictsPageView', () => {
  it('renders the latest answer and every earlier verdict', () => {
    const html = render({
      latest: {
        runId: 'r1',
        question: 'Should we expand into the European market in 2027?',
        view: view!,
        sources: ['eu-market-2027.pdf'],
        corpusMissing: false,
      },
      earlier: [{ runId: 'r0', question: 'Should we hire?', stance: 'POSITIVE', share: 0.74, date: '2026-10-09T10:00:00Z' }],
    })
    expect(html).toContain('Should we expand into the European market in 2027?')
    expect(html).toContain('Should we hire?')
    expect(html).toContain('0.74')
    expect(html).toContain('/runs/r0')
  })

  it('renders the empty state and the failure state', () => {
    expect(render({ latest: null, earlier: [] })).toContain('Your first answer appears here')
    const failed = render({ latest: null, earlier: [], failed: true })
    expect(failed).toContain('reach the server')
    expect(failed).toContain('Try again')
  })

  it('carries no banned word', () => {
    expect(renderedText(render())).not.toMatch(BANNED_WORD)
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('loadVerdicts', () => {
  it('keeps the readable verdicts when one run cannot be read', async () => {
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
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/r-bad')) return reply({ detail: 'not found' }, false, 404)
        if (url.includes('/r-good')) return reply(good)
        return reply({
          items: [run({ run_id: 'r-bad', query: 'A run whose record is gone' }), run({ run_id: 'r-good' })],
          next_cursor: null,
        })
      }),
    )
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const loaded = await loadVerdicts()

    expect(loaded.latest?.runId).toBe('r-good')
    expect(loaded.latest?.sources).toEqual(['eu-market-2027.pdf'])
    expect(loaded.earlier).toEqual([])
    expect(errorSpy).toHaveBeenCalled()
  })
})
