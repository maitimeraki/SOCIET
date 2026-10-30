import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { OverviewPageView, monthKeyUtc } from './OverviewPage'
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

  it('renders no banned word', () => {
    expect(renderedText(view())).not.toMatch(BANNED_TERMS)
  })
})

describe('the month the page measures', () => {
  it('derives the key from the clock in UTC', () => {
    expect(monthKeyUtc(new Date('2026-10-31T23:30:00Z'))).toBe('2026-10')
    expect(monthKeyUtc(new Date('2026-11-01T00:30:00Z'))).toBe('2026-11')
  })
})
