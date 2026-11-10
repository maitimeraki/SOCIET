import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { BillingUsage, RunSummary } from '../api/types'
import { OverviewPageView, greetingName, recentRows, recentState } from './OverviewPage'
import { BANNED_TERMS, renderedText } from '../test/copyLaw'

const NOOP = () => {}

// Server truth for the page's only usage source (`GET /api/v1/billing/usage`).
const STATS: BillingUsage = {
  plan: 'starter',
  units_total: 5000,
  units_used: 3200,
  units_remaining: 1800,
  period_start: '2026-10-01T00:00:00Z',
  period_end: '2026-11-01T00:00:00Z',
  limits: { max_agents: 20, max_rounds: 4 },
  billing_enabled: false,
}

// The view carries `<Link>`s, and react-router's `Link` needs a router context even under SSR —
// the wrapper is the same one every page-view test in this repo uses (DocumentsPage.test.tsx).
const view = (over: Partial<Parameters<typeof OverviewPageView>[0]> = {}) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <OverviewPageView
        stats={STATS}
        filed={3}
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
    expect(html.indexOf('Units used')).toBeLessThan(html.indexOf('Recent work'))
  })

  it('greets the signed-in account, and invents no name when there is none', () => {
    expect(view({ accountName: 'Anupam' })).toContain('Good morning, Anupam.')
    expect(view()).toContain('Good morning.')
    expect(view()).not.toContain('Anupam')
  })

  it('gives every standalone link a 44px target (§10.4)', () => {
    const html = view({
      recent: [
        { runId: 'r1', question: 'Renew the lease?', state: 'Filed', stance: 'NEGATIVE', share: 0.82, passes: '4', date: '2026-10-22' },
      ],
    })
    const standalone = [...html.matchAll(/<a\b[^>]*>/g)]
      .map((match) => match[0])
      .filter((tag) => /href="\/(?:runs|documents|pricing)"/.test(tag))
    expect(standalone.length).toBeGreaterThanOrEqual(4)
    for (const tag of standalone) expect(tag).toContain('min-h-11')
  })

  it('reads the live filed count in the state line', () => {
    expect(view()).toContain('Nothing is running. 3 answers filed and waiting for you.')
    expect(
      view({ working: { runId: 'r1', question: 'q', passes: '2 of 5', note: 'Pass 2 of 5.', convergence: null } }),
    ).toContain('One question is with the panel. 3 filed and waiting for you.')
  })

  it('carries all five sections', () => {
    const html = view()
    expect(html).toContain('Units used')
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

  it('states the plan and the room left on it, from the server values', () => {
    const html = view()
    expect(html).toContain('Units used')
    expect(html).toContain('3,200')
    expect(html).toContain('of 5,000')
    expect(html).toContain('Units remaining')
    expect(html).toContain('1,800')
    expect(html).toContain('Starter')
    expect(html).toContain('Resets 1 Nov 2026')
    expect(html).toContain('Manage plan')
  })

  it('renders no invented meter, example label or literal plan name', () => {
    const html = view()
    expect(html).not.toContain('Corpus')
    expect(html).not.toContain('Deep decisions')
    expect(html).not.toContain('Example')
    expect(html).not.toContain('Studio')
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
    // §4.7 — recent-work rows are records: their boundary is the record rule, not the decorative
    // hairline (the stats band's tile dividers stay decorative).
    const rows = [...html.matchAll(/<article[^>]*>/g)].map((match) => match[0])
    expect(rows).toHaveLength(4)
    for (const row of rows) expect(row).toContain('border-t border-rule')
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

  it('feeds recent work from the whole history, not only the current month', () => {
    const rows = recentRows([
      run({ run_id: 'old', created_at: '2026-09-30T10:00:00Z', verdict_stance: 'POSITIVE' }),
      run({ run_id: 'new', created_at: '2026-11-01T00:05:00Z' }),
    ])
    expect(rows.map((row) => row.runId)).toEqual(['old', 'new'])
    expect(rows[0].state).toBe('Filed')
    expect(rows[0].date).toBe('30 Sept 2026')
  })
})

describe('the greeting name comes from the session, never from the page', () => {
  it('reads the email local part and capitalises it', () => {
    expect(greetingName('anupam@example.com')).toBe('Anupam')
    expect(greetingName('anupam.sharma@example.com')).toBe('Anupam')
  })

  it('renders no name for an empty or missing address', () => {
    expect(greetingName('')).toBe('')
  })
})
