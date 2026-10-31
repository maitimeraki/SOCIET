import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { RunSummary } from '../api/types'
import { BANNED_TERMS, renderedText } from '../test/copyLaw'
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
  verdict_confidence: null,
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
    expect(html).toContain('Negative')
    expect(html).toContain('Complete')
    expect(html).toContain('/runs/r1')
  })

  it('marks a running run and withholds its outcome', () => {
    const html = render({ runs: [run({ status: 'running', verdict_stance: null, rounds_executed: 2 })] })
    expect(html).toContain('Deliberating')
    expect(html).toContain('pass 2')
    expect(html).not.toContain('Negative')
  })

  it('never reads a failed or interrupted run as live work', () => {
    const html = render({
      runs: [
        run({ run_id: 'f1', status: 'failed', verdict_stance: null, rounds_executed: 2 }),
        run({ run_id: 'i1', status: 'interrupted', verdict_stance: null, rounds_executed: 3 }),
      ],
    })
    expect(html).toContain('Failed')
    expect(html).toContain('Interrupted')
    expect(html).not.toContain('Deliberating')
  })

  it('renders the empty and failed states', () => {
    expect(render({ runs: [] })).toContain('No decisions yet')
    const failed = render({ runs: [], failed: true })
    expect(failed).toContain('reach the server')
    expect(failed).toContain('Try again')
  })

  it('keeps the archive when a later page fails, offering only a compact retry', () => {
    const html = render({ runs: [run()], failed: true, hasMore: true })
    expect(html).toContain('Should we renew the lease?')
    expect(html).toContain('Couldn&#x27;t load more.')
    expect(html).not.toContain('reach the server')
    expect(html).not.toContain('Load more')
  })

  it('still shows the full failure state when nothing loaded', () => {
    const html = render({ runs: [], failed: true, hasMore: true })
    expect(html).toContain('reach the server')
    expect(html).not.toContain('Couldn&#x27;t load more.')
  })

  it('carries no banned word', () => {
    expect(renderedText(render({ runs: [run()] }))).not.toMatch(BANNED_TERMS)
  })
})

describe('the runs list', () => {
  it('shows the filed share from the list, without reading every run', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <RunsPageView
          runs={[
            {
              run_id: 'r1',
              query: 'Should Ridgeline Coffee open a second location on Mill Street?',
              status: 'complete',
              rounds_executed: 4,
              verdict_stance: 'NEGATIVE',
              verdict_confidence: 0.82,
              corpus_label: 'Mill Street expansion',
              dataset_id: 'd1',
              converged: true,
              created_at: '2026-10-22T09:00:00+00:00',
            },
          ]}
          loading={false}
          failed={false}
          hasMore={false}
          loadingMore={false}
          onLoadMore={() => {}}
          onRetry={() => {}}
        />
      </MemoryRouter>,
    )
    expect(html).toContain('0.82')
    expect(html).toContain('Negative')
    expect(html).toContain('pass 4')
  })

  it('groups the rows by month, newest month first', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <RunsPageView
          runs={[
            {
              run_id: 'r1',
              query: 'a',
              status: 'complete',
              rounds_executed: 3,
              verdict_stance: null,
              verdict_confidence: null,
              corpus_label: null,
              dataset_id: 'd1',
              converged: true,
              created_at: '2026-09-04T09:00:00+00:00',
            },
            {
              run_id: 'r2',
              query: 'b',
              status: 'complete',
              rounds_executed: 4,
              verdict_stance: 'POSITIVE',
              verdict_confidence: 0.74,
              corpus_label: null,
              dataset_id: 'd1',
              converged: true,
              created_at: '2026-10-18T09:00:00+00:00',
            },
          ]}
          loading={false}
          failed={false}
          hasMore={false}
          loadingMore={false}
          onLoadMore={() => {}}
          onRetry={() => {}}
        />
      </MemoryRouter>,
    )
    expect(html).toContain('October 2026')
    expect(html).toContain('September 2026')
    expect(html.indexOf('October 2026')).toBeLessThan(html.indexOf('September 2026'))
  })
})
