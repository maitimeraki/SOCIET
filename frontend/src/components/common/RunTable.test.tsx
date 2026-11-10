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
  verdict_confidence: null,
}

const render = (runs: RunSummary[], loading = false) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <RunTable runs={runs} loading={loading} />
    </MemoryRouter>,
  )

describe('RunTable — the decision list (§8.4)', () => {
  it('leads with the question as a heading inside the card link', () => {
    const html = render([RUN])
    expect(html).toContain('<h3')
    expect(html).toMatch(/<h3[^>]*>Should we expand into Europe\?<\/h3>/)
    expect(html).toContain('href="/runs/r1"')
    expect(html).not.toContain('<table') // a list of decisions, not a data table
  })

  it('maps the real payload fields — created_at, query, rounds_executed, status', () => {
    const html = render([RUN])
    // `created_at` → `fmtDate`, asserted as the exact local-time literal (`TZ` pinned to UTC in
    // vite.config.ts) — a formatter bug is caught, not just a comparison against `fmtDate` itself.
    expect(html).toContain('1 Oct 2026 10:00')
    expect(html).toContain('Should we expand into Europe?') // question → query
    expect(html).toContain('3 passes') // passes → rounds_executed, the payload's own count
    expect(html).toContain('Complete') // status → StateChip's word
  })

  it('shows the corpus by its label, falling back to the corpus id', () => {
    expect(render([RUN])).toContain('Europe expansion') // corpus_label when present
    expect(render([{ ...RUN, corpus_label: null }])).toContain('ds-1') // the corpus id, else
  })

  it('renders the outcome as the stance word beside its symbol', () => {
    // StanceChip draws symbol + colour + word together (§6/§9); the word is what proves the stance
    // is not a bare hue.
    expect(render([RUN])).toContain('Positive')
  })

  it('says "still running" when a run is still going and has no verdict yet', () => {
    const html = render([{ ...RUN, status: 'running', verdict_stance: null }])
    expect(html).toContain('still running')
    expect(html).not.toContain('No outcome yet')
    expect(html).not.toContain('Positive') // no outcome claimed before one exists
  })

  it('says "No outcome yet" — never "still running" — for a finished run with no verdict', () => {
    // A failed run has ENDED without a verdict: the outcome must not claim it is still going, or it
    // would contradict the Status chip right beside it.
    const html = render([{ ...RUN, status: 'failed', verdict_stance: null }])
    expect(html).toContain('No outcome yet')
    expect(html).not.toContain('still running')
    expect(html).toContain('Failed') // the status chip is unchanged
  })

  it('says "No outcome yet" for an interrupted run with no verdict', () => {
    const html = render([{ ...RUN, status: 'interrupted', verdict_stance: null }])
    expect(html).toContain('No outcome yet')
    expect(html).not.toContain('still running')
    expect(html).toContain('Interrupted')
  })

  it('renders an honest dash when the run names neither a corpus label nor an id', () => {
    // `run_doc._summarize` can return `dataset_id: None`; the corpus line must not throw or blank.
    const html = render([{ ...RUN, corpus_label: null, dataset_id: null as unknown as string }])
    expect(html).toContain('—')
    expect(html).toContain('Should we expand into Europe?') // the card still renders — no throw
  })

  it('links the whole card to the run', () => {
    expect(render([RUN])).toContain('href="/runs/r1"')
  })

  it('never renders an "Agents" word', () => {
    // The card fields above replace the old agent-count dash (§13 bans the word itself).
    expect(render([RUN])).not.toContain('Agents')
  })

  it('uses the same card list at every width — no separate table for desktop', () => {
    const html = render([RUN])
    expect(html).not.toContain('<table')
    expect(html).not.toContain('md:hidden')
    expect(html).toContain('Should we expand into Europe?')
  })

  it('renders nothing for an empty list — the caller owns the empty state', () => {
    expect(render([])).toBe('')
  })

  it('renders skeletons while loading, not an empty list', () => {
    const html = render([], true)
    expect(html).not.toContain('Should we expand into Europe?')
    expect(html.length).toBeGreaterThan(0)
  })
})
