import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { RunSummary } from '../api/types'
import { OverviewPageView, monthKeyUtc, recentState } from './OverviewPage'
import { BANNED_TERMS, renderedText } from '../test/copyLaw'

const NOOP = () => {}

// The view carries `<Link>`s, and react-router's `Link` needs a router context even under SSR —
// the wrapper is the same one every page-view test in this repo uses (DocumentsPage.test.tsx).
const view = (over: Partial<Parameters<typeof OverviewPageView>[0]> = {}) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <OverviewPageView
        stats={{ decisions: 5, filed: 3, corpusBytes: 620_000_000, corpusLimit: 2_000_000_000, decisionsLeft: 15, decisionsLimit: 20 }}
        recent={[]}
        corpora={[{ name: 'Mill Street expansion', documents: 5, read: 4, reading: 1, lastUsed: '2026-10-22T09:00:00+00:00' }]}
        working={null}
        loading={false}
        failed={false}
        onRetry={NOOP}
        {...over}
      />
    </MemoryRouter>,
  )

describe('the Overview', () => {
  it('answers the question before any prose', () => {
    const html = view()
    expect(html).toContain('Good morning')
    expect(html.indexOf('Decisions this month')).toBeLessThan(html.indexOf('Recent work'))
  })

  it('reads the live filed count in the state line', () => {
    expect(view()).toContain('Nothing is running. 3 answers filed and waiting for you.')
    expect(
      view({ working: { runId: 'r1', question: 'q', passes: '2 of 5', note: 'Pass 2 of 5.', convergence: null } }),
    ).toContain('One question is with the panel. 3 filed and waiting for you.')
  })

  it('carries all five sections', () => {
    const html = view()
    expect(html).toContain('Decisions this month')
    expect(html).toContain('Recent work')
    expect(html).toContain('Your material')
    expect(html).toContain('Plan &amp; usage')
    expect(html).toContain('Working now')
  })

  it('lists the corpora as a ruled record, not a card grid', () => {
    const html = view()
    expect(html).toContain('Mill Street expansion')
    expect(html).toContain('5 documents')
    expect(html).toContain('1 reading')
    expect(html).toContain('divide-rule')
  })

  it('states the plan and the room left on it', () => {
    const html = view()
    expect(html).toContain('Corpus')
    expect(html).toContain('620 MB')
    expect(html).toContain('of 2 GB')
    expect(html).toContain('Deep decisions')
    expect(html).toContain('15')
    expect(html).toContain('of 20')
    expect(html).toContain('Manage plan')
  })

  it('opens each decision at its own address', () => {
    const html = view({
      recent: [
        { runId: 'r1', question: 'Renew the lease?', state: 'Filed', stance: 'NEGATIVE', share: 0.82, passes: '4', date: '2026-10-22' },
        { runId: 'r2', question: 'Open Mill Street?', state: 'Deliberating', stance: null, share: null, passes: '2', date: '2026-10-23' },
        { runId: 'r3', question: 'Hire a roaster?', state: 'Failed', stance: null, share: null, passes: '1', date: '2026-10-24' },
        { runId: 'r4', question: 'Buy the roastery?', state: 'Interrupted', stance: null, share: null, passes: '3', date: '2026-10-25' },
      ],
    })
    expect(html).toContain('href="/runs/r1/verdict"')
    expect(html).toContain('href="/runs/r2"')
    expect(html).toContain('href="/runs/r3"')
    expect(html).toContain('href="/runs/r4"')
    expect(html).toContain('Failed')
    expect(html).toContain('Interrupted')
    expect(html).toContain('pass 2')
  })

  it('renders no banned word', () => {
    expect(renderedText(view())).not.toMatch(BANNED_TERMS)
  })
})

describe('the state a recent run is written in', () => {
  const run = (over: Partial<RunSummary>): RunSummary => ({
    run_id: 'r1',
    created_at: '2026-10-02T10:00:00Z',
    query: 'q',
    corpus_label: null,
    dataset_id: 'd1',
    status: 'complete',
    rounds_executed: 2,
    converged: true,
    verdict_stance: null,
    verdict_confidence: null,
    ...over,
  })

  it('reads a run that filed an answer as Filed', () => {
    expect(recentState(run({ verdict_stance: 'NEGATIVE' }))).toBe('Filed')
  })

  it('reads an ended run as ended, never as still working', () => {
    expect(recentState(run({ status: 'failed' }))).toBe('Failed')
    expect(recentState(run({ status: 'interrupted' }))).toBe('Interrupted')
    expect(recentState(run({ status: 'cancelled' }))).toBe('Cancelled')
    expect(recentState(run({ status: 'running' }))).toBe('Deliberating')
  })
})

describe('the month the page measures', () => {
  it('derives the key from the clock in UTC', () => {
    expect(monthKeyUtc(new Date('2026-10-31T23:30:00Z'))).toBe('2026-10')
    expect(monthKeyUtc(new Date('2026-11-01T00:30:00Z'))).toBe('2026-11')
  })
})
