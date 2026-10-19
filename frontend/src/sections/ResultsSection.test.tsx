import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { VerdictView } from '../run/selectors'
import { ResultsView } from './ResultsSection'
import type { ResultsViewProps } from './ResultsSection'
// §13 — the one copy-law guard, shared with every rendered-string test.
import { BANNED_WORD, renderedText } from '../test/copyLaw'

// Node-only (no jsdom) and `useEffect` does not run under `renderToStaticMarkup`, so the section is
// split like `DocumentsSection`/`RunsSection`: `ResultsView` is state-free and prop-driven, asserted
// here; the default export owns the fetch.
const view = (): VerdictView => ({
  stance: 'POSITIVE',
  confidence: 0.82,
  converged: true,
  summary: 'Aggregate reading: lean positive.',
  narrative: '',
  narrativeStatus: 'fallback',
  dissentingViews: [{ stance: 'NEGATIVE', view: 'Cash flow is too tight this year.' }],
  evidence: [],
  clusters: [],
  finalStances: [{ agent: 'Nordic Lead', stance: 'POSITIVE' }],
  supporting: ['Nordic demand'],
  opposing: [],
  warnings: [],
})

const render = (props: Partial<ResultsViewProps> = {}) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <ResultsView
        runId={null}
        question=""
        view={null}
        sources={[]}
        corpusMissing={false}
        loading={false}
        failed={false}
        onRetry={() => {}}
        {...props}
      />
    </MemoryRouter>,
  )

describe('ResultsSection — §8.5 Verdicts', () => {
  it('renders the newest completed decision’s answer', () => {
    const html = render({
      runId: 'r1',
      question: 'Should we expand into Europe?',
      view: view(),
      sources: ['Market research 2026'],
    })
    expect(html).toContain('Should we expand into Europe?') // the decision
    expect(html).toContain('Cash flow is too tight this year.') // the case against
    expect(html).toContain('Market research 2026') // a source
  })

  it('shows an honest empty state when nothing has completed', () => {
    const html = render()
    expect(html).toContain('A verdict appears here when a decision finishes.')
    expect(html).not.toContain('Export this verdict') // never a document with nothing in it
  })

  it('renders a real error with a retry on failure, never the empty state', () => {
    // The rendered apostrophe is entity-escaped by `renderToStaticMarkup`, so assert an unescaped span.
    const html = render({ failed: true })
    expect(html).toContain('reach the server')
    expect(html).toContain('Try again')
    expect(html).not.toContain('A verdict appears here')
  })

  it('carries the server message into the failure detail, standing copy when there is none', () => {
    expect(render({ failed: true, failDetail: 'API 500: the answer is unavailable' })).toContain(
      'API 500: the answer is unavailable',
    )
    expect(render({ failed: true })).toContain('load when the server is back')
  })

  it('renders skeletons while loading, never the empty state', () => {
    const html = render({ loading: true })
    expect(html).not.toContain('A verdict appears here')
    expect(html).not.toContain('Export this verdict')
  })
})

describe('the copy law (§13) holds on Verdicts when loaded, empty or failed', () => {
  it('renders no banned word in any state', () => {
    expect(
      renderedText(render({ runId: 'r1', question: 'Should we expand into Europe?', view: view(), sources: ['Market research 2026'] })),
    ).not.toMatch(BANNED_WORD)
    expect(renderedText(render())).not.toMatch(BANNED_WORD)
    expect(renderedText(render({ failed: true }))).not.toMatch(BANNED_WORD)
  })
})
