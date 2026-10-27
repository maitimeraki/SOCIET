import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { RunSummary } from '../api/types'
import { BANNED_WORD, renderedText } from '../test/copyLaw'
import { RunsPageView, type RunsPageViewProps } from './RunsPage'

const run = (patch: Partial<RunSummary> = {}): RunSummary => ({
  run_id: 'r1',
  created_at: '2026-10-12T10:00:00Z',
  query: 'Should we renew the lease?',
  corpus_label: 'Mill Street',
  dataset_id: 'd1',
  status: 'complete',
  rounds_executed: 3,
  converged: true,
  verdict_stance: 'NEGATIVE',
  ...patch,
})

const render = (props: Partial<RunsPageViewProps> = {}) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <RunsPageView
        runs={[]}
        loading={false}
        failed={false}
        hasMore={false}
        loadingMore={false}
        onLoadMore={() => {}}
        onRetry={() => {}}
        {...props}
      />
    </MemoryRouter>,
  )

describe('RunsPageView', () => {
  it('renders every run with its outcome and status', () => {
    const html = render({ runs: [run()] })
    expect(html).toContain('Should we renew the lease?')
    expect(html).toContain('NEGATIVE')
    expect(html).toContain('Complete')
    expect(html).toContain('/runs/r1')
  })

  it('marks a running run and withholds its outcome', () => {
    const html = render({ runs: [run({ status: 'running', verdict_stance: null, rounds_executed: 2 })] })
    expect(html).toContain('still running')
    expect(html).toContain('2 passes')
    expect(html).not.toContain('NEGATIVE')
  })

  it('renders the empty and failed states', () => {
    expect(render({ runs: [] })).toContain('No decisions yet')
    const failed = render({ runs: [], failed: true })
    expect(failed).toContain('reach the server')
    expect(failed).toContain('Try again')
  })

  it('carries no banned word', () => {
    expect(renderedText(render({ runs: [run()] }))).not.toMatch(BANNED_WORD)
  })
})
