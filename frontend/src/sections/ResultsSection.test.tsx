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
// here; the default export owns the subject walk and the fetch. The subject is the newest decision
// that has filed an answer — the same subject Your panel describes.
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
        pendingRunId={null}
        loading={false}
        failed={false}
        onRetry={() => {}}
        {...props}
      />
    </MemoryRouter>,
  )

describe('ResultsSection — The last answer', () => {
  it('opens with the filed sheet: question, position, the weighted share, the case against, the sources', () => {
    const html = render({
      runId: 'r1',
      question: 'Should we expand into Europe?',
      view: view(),
      sources: ['Market research 2026'],
    })
    expect(html).toContain('Should we expand into Europe?') // the decision
    expect(html).toContain('POSITIVE') // the position, as symbol + word
    expect(html).toContain('0.82') // the weighted share
    expect(html).toContain('The case against')
    expect(html).toContain('Cash flow is too tight this year.') // the case against, in words
    expect(html).toContain('Market research 2026') // a source
    // It is the kit's filed sheet: a card (canvas + shadow), not a card-shaped summary line.
    expect(html).toContain('bg-canvas')
    expect(html).toContain('shadow-raised')
  })

  it('reads the document prose in the reading face, below the sheet', () => {
    const html = render({ runId: 'r1', question: 'Q', view: view(), sources: [] })
    expect(html).toContain('font-record')
    expect(html).toContain('text-body-lg')
    expect(html).toContain('Weighted confidence')
  })

  it('says plainly that the newest decision has not filed an answer yet, and links it', () => {
    const html = render({ pendingRunId: 'r9' })
    expect(html).toContain('This decision has not filed an answer yet.')
    expect(html).toContain('href="/runs/r9"')
    expect(html).toContain('Open this decision')
    expect(html).not.toContain('Export this verdict') // never a document with nothing in it
  })

  it('shows an honest empty state with the one next action when there is no decision at all', () => {
    const html = render()
    expect(html).toContain('Your first answer appears here when a decision files one.')
    expect(html).toContain('href="/new"') // the primitive's action slot, not a bare paragraph
    expect(html).toContain('Start free')
    expect(html).not.toContain('Export this verdict')
  })

  it('renders a real error with a retry on failure, never the empty state', () => {
    // The rendered apostrophe is entity-escaped by `renderToStaticMarkup`, so assert an unescaped span.
    const html = render({ failed: true })
    expect(html).toContain('reach the server')
    expect(html).toContain('Try again')
    expect(html).not.toContain('Your first answer appears here')
  })

  it('carries the server message into the failure detail, standing copy when there is none', () => {
    expect(render({ failed: true, failDetail: 'API 500: the answer is unavailable' })).toContain(
      'API 500: the answer is unavailable',
    )
    expect(render({ failed: true })).toContain('loads when the server is back')
  })

  it('renders a sheet-shaped skeleton while loading, never the empty state', () => {
    const html = render({ loading: true })
    expect(html).toContain('animate-pulse')
    expect(html).not.toContain('Your first answer appears here')
    expect(html).not.toContain('Export this verdict')
  })
})

describe('the copy law (§13) holds on The last answer when loaded, empty or failed', () => {
  it('renders no banned word in any state', () => {
    expect(
      renderedText(render({ runId: 'r1', question: 'Should we expand into Europe?', view: view(), sources: ['Market research 2026'] })),
    ).not.toMatch(BANNED_WORD)
    expect(renderedText(render())).not.toMatch(BANNED_WORD)
    expect(renderedText(render({ pendingRunId: 'r9' }))).not.toMatch(BANNED_WORD)
    expect(renderedText(render({ failed: true }))).not.toMatch(BANNED_WORD)
  })
})
