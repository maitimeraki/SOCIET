import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { AgentProfile } from '../run/events'
import { PanelView } from './PanelSection'
import type { PanelViewProps } from './PanelSection'
// §13 — the one copy-law guard, shared with every rendered-string test.
import { BANNED_WORD, renderedText } from '../test/copyLaw'

// Node-only (no jsdom) and `useEffect` does not run under `renderToStaticMarkup`, so the section is
// split like `DocumentsSection`/`RunsSection`: `PanelView` is state-free and prop-driven, asserted
// here; the default export owns the fetch. Experts exist only inside a decision — there is no
// cross-decision identity for them — so the section's own honesty notice leads and is asserted too.
const expert = (patch: Partial<AgentProfile> = {}): AgentProfile => ({
  agent_id: 'a1',
  identity: { name: 'Nordic Lead', archetype: 'Analyst', communication_style: 'Measured' },
  bio: 'Weighs demand signals against the cost base.',
  detailed_perspective: 'I read the demand curve first.',
  stance: 'POSITIVE',
  intensity: 0.6,
  confidence: 0.72,
  conviction: 0.58,
  cior: 0.2,
  domain_tags: ['market'],
  communication_radius: 1,
  summary_provenance: [{ doc_id: 'd1', title: 'Market research 2026', chunk_id: 'c1' }],
  confidence_breakdown: { source_breadth: 3, node_density: 4, relationship_connectivity: 2 },
  ...patch,
})

const render = (props: Partial<PanelViewProps> = {}) =>
  renderToStaticMarkup(<PanelView experts={[]} loading={false} failed={false} onRetry={() => {}} {...props} />)

describe('PanelSection — §8.6 Panel', () => {
  it('states what it can show and what it cannot yet show', () => {
    const html = render()
    // What it can: the panel of the most recent decision, from the reader's own documents.
    expect(html).toContain('most recent decision')
    expect(html).toContain('your own documents')
    // What it cannot: a panel that persists, or any history across decisions.
    expect(html).toContain('cannot yet show')
    expect(html).toContain('does not carry over')
  })

  it('renders the experts of the most recent decision with their argued positions and sources', () => {
    const html = render({
      experts: [
        expert(),
        expert({
          agent_id: 'a2',
          identity: { name: 'Risk Lead', archetype: 'Analyst', communication_style: 'Blunt' },
          stance: 'NEGATIVE',
          summary_provenance: [{ doc_id: 'd2', title: 'CFO memo', chunk_id: 'c9' }],
        }),
      ],
    })
    expect(html).toContain('Nordic Lead') // the expert
    expect(html).toContain('POSITIVE') // the position it argued — the stance word, per the legend
    expect(html).toContain('Market research 2026') // a document it argued from
    expect(html).toContain('Risk Lead')
    expect(html).toContain('NEGATIVE')
    expect(html).toContain('CFO memo')
    // The list carries an accessible name (a heading it is labelled by), so it is navigable.
    expect(html).toContain('aria-labelledby="panel-experts"')
    expect(html).toContain('Who argued it')
  })

  it('lists each document once, however many links point to it', () => {
    const html = render({
      experts: [
        expert({
          summary_provenance: [
            { doc_id: 'd1', title: 'Market research 2026', chunk_id: 'c1' },
            { doc_id: 'd1', title: 'Market research 2026', chunk_id: 'c2' },
          ],
        }),
      ],
    })
    expect(html.match(/Market research 2026/g)).toHaveLength(1)
  })

  it('says so for each expert when none of their documents is recorded, never a silent blank', () => {
    const html = render({ experts: [expert({ summary_provenance: [] })] })
    expect(html).toContain('No documents recorded for this expert')
  })

  it('shows an honest empty state when there is no decision yet', () => {
    const html = render({ experts: [] })
    expect(html).toContain('No panel yet')
  })

  it('renders a real error with a retry on failure, never the empty state', () => {
    const html = render({ experts: [], failed: true })
    expect(html).toContain('reach the server')
    expect(html).toContain('Try again') // the retry affordance
    expect(html).not.toContain('No panel yet') // never the empty state on failure
  })

  it('carries the server message into the failure detail, standing copy when there is none', () => {
    expect(render({ experts: [], failed: true, failDetail: 'API 500: the panel is unavailable' })).toContain(
      'API 500: the panel is unavailable',
    )
    // No message forwarded → the view's own copy, never an empty detail.
    expect(render({ experts: [], failed: true })).toContain('when the server is back')
  })

  it('renders skeletons while loading, never the empty state', () => {
    const html = render({ experts: [], loading: true })
    expect(html).toContain('animate-pulse') // the loading placeholders are actually rendered
    expect(html).not.toContain('No panel yet') // ...and never the empty state
  })
})

describe('the copy law (§13) holds on the Panel when loaded, empty or failed', () => {
  it('renders no banned word in any state', () => {
    expect(renderedText(render({ experts: [expert()] }))).not.toMatch(BANNED_WORD)
    expect(renderedText(render({ experts: [] }))).not.toMatch(BANNED_WORD)
    expect(renderedText(render({ experts: [], failed: true }))).not.toMatch(BANNED_WORD)
  })
})
