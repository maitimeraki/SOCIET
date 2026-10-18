import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { RunSummary } from '../../api/types'
import RunTable from './RunTable'

const RUN: RunSummary = {
  run_id: 'r1',
  created_at: '2026-10-01T10:00:00Z',
  query: 'Should we expand into Europe?',
  corpus_label: 'Europe expansion',
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

describe('RunTable — the decision list columns (§8.4)', () => {
  it('renders the six columns: when · question · corpus · passes · outcome · status', () => {
    const html = render([RUN])
    for (const header of ['When', 'Question', 'Corpus', 'Passes', 'Outcome', 'Status']) {
      expect(html).toContain(header)
    }
  })

  it('maps the real payload fields — created_at, query, rounds_executed, status', () => {
    const html = render([RUN])
    // `created_at` → `fmtDate`, asserted as the exact local-time literal (`TZ` pinned to UTC in
    // vite.config.ts) — a formatter bug is caught, not just a comparison against `fmtDate` itself.
    expect(html).toContain('1 Oct 2026 10:00')
    expect(html).toContain('Should we expand into Europe?') // question → query
    expect(html).toContain('>3<') // passes → rounds_executed, the payload's own count
    expect(html).toContain('Complete') // status → StateChip's word
  })

  it('shows the corpus by its label, falling back to the corpus id', () => {
    expect(render([RUN])).toContain('Europe expansion') // corpus_label when present
    expect(render([{ ...RUN, corpus_label: null }])).toContain('ds-1') // the corpus id, else
  })

  it('renders the outcome as the stance word beside its symbol', () => {
    // StanceChip draws symbol + colour + word together (§6/§9); the word is what proves the stance
    // is not a bare hue.
    expect(render([RUN])).toContain('POSITIVE')
  })

  it('renders an honest "still running" when there is no verdict yet, never a blank cell', () => {
    const html = render([{ ...RUN, verdict_stance: null }])
    expect(html).toContain('still running')
    expect(html).not.toContain('POSITIVE') // no outcome claimed before one exists
  })

  it('links each row to the run', () => {
    expect(render([RUN])).toContain('href="/runs/r1"')
  })

  it('never renders an "Agents" column', () => {
    // The column set above replaces the old agent-count dash (§13 bans the word itself).
    expect(render([RUN])).not.toContain('Agents')
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
