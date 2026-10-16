import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { RunSummary } from '../../api/types'
import RunTable from './RunTable'

const RUN: RunSummary = {
  run_id: 'r1',
  created_at: '2026-10-01T10:00:00Z',
  query: 'Should we expand into Europe?',
  dataset_id: 'ds-1',
  status: 'complete',
  rounds_executed: 3,
  converged: true,
  verdict_stance: 'POSITIVE',
}

const render = (runs: RunSummary[], loading = false) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <RunTable runs={runs} loading={loading} />
    </MemoryRouter>,
  )

describe('RunTable — the run timeline columns (§3.3)', () => {
  it('renders the five columns: timestamp · question · documents used · status · agent count', () => {
    const html = render([RUN])
    for (const header of ['Timestamp', 'Question', 'Documents used', 'Status', 'Agents']) {
      expect(html).toContain(header)
    }
  })

  it('maps the real fields — created_at, query, dataset_id, status', () => {
    const html = render([RUN])
    expect(html).toContain('1 Oct 2026')
    expect(html).toContain('Should we expand into Europe?')
    expect(html).toContain('ds-1') // the corpus the run drew from
    expect(html).toContain('Complete') // StateChip's word, ink — the symbol carries the hue
  })

  it('renders the absent agent count as an honest dash, never an invented value', () => {
    // `run_doc._summarize` carries no agent count — the column must not fabricate one.
    expect(render([RUN])).toContain('—')
  })

  it('collapses to stacked cards under md — the same rows, a second layout', () => {
    const html = render([RUN])
    expect(html).toContain('md:hidden') // the card list
    expect(html).toContain('hidden overflow-x-auto md:block') // the table
  })

  it('renders nothing for an empty list — the caller owns the empty state', () => {
    expect(render([])).toBe('')
  })

  it('renders skeletons while loading, not an empty table', () => {
    const html = render([], true)
    expect(html).not.toContain('<table')
    expect(html.length).toBeGreaterThan(0)
  })
})
