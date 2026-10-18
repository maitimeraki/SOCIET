import { beforeEach, describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see Workspace.test.tsx / GraphCanvas.test.tsx): the
// suite runs in Node, so `useEffect` never runs and no click or key can be dispatched. The drawer is
// therefore split into the pure derivations (`entryDetails`, `resolveSelection`), an exported
// state-free view, and a store-reading default export — the tests drive each of those directly.
// "Esc closes" and "focus returns to the map" are NOT DOM-assertable: they belong to `Drawer`'s
// `useModalA11y` and hold by construction (it restores focus to the opener — the map, which the
// canvas focuses as it opens the drawer). They are asserted structurally (a real modal dialog) and
// stated as construction in the report, never faked with a simulated click.
import { renderToStaticMarkup } from 'react-dom/server'
import { EXPERT_TYPE } from '../../graph/graphStore'
import type { GraphEdge, GraphNode } from '../../graph/graphStore'
import { useSelectionStore } from '../../graph/selectionStore'
import { fold } from '../../run/reducer'
import type { AgentProfile, ProvenanceLink, RunEvent, Stance } from '../../run/events'
import { NodeDetailsView, entryDetails, resolveSelection } from './NodeDetailsDrawer'
import type { MapDetails } from './NodeDetailsDrawer'

const OPINION_TYPE = 'Opinion'

function profile(name: string, stance: Stance, sources: ProvenanceLink[]): AgentProfile {
  return {
    agent_id: name,
    identity: { name, archetype: 'Trade analyst', communication_style: 'measured' },
    bio: `${name} reads the record closely.`,
    detailed_perspective: 'I read the record as a trade analyst.',
    stance,
    intensity: 0.6,
    confidence: 0.7,
    conviction: 0.65,
    cior: 0.4,
    domain_tags: ['trade'],
    communication_radius: 1,
    summary_provenance: sources,
    confidence_breakdown: { source_breadth: 2, node_density: 5, relationship_connectivity: 0.6 },
  }
}

const EXPANSION: ProvenanceLink = {
  doc_id: 'doc-1',
  title: 'European Expansion Analysis.pdf',
  breadcrumb: 'Market outlook',
  chunk_id: 'chunk-1',
}
const EXPANSION_DISTRIBUTION: ProvenanceLink = { ...EXPANSION, breadcrumb: 'Distribution', chunk_id: 'chunk-2' }
const COMPETITORS: ProvenanceLink = { doc_id: 'doc-2', title: 'competitor-research.md', chunk_id: 'chunk-3' }

const turn = (name: string, stance: string, confidence: number, content: string, references: string[]) => ({
  agent_id: name,
  agent_name: name,
  content,
  stance,
  confidence,
  references,
})

/** A run with a material entry two experts cite, an expert with sources, and one filed opinion. */
const EVENTS: RunEvent[] = [
  // The dataset id rides the pair id; the run folds it into state.
  { type: 'pair_turn', pair_id: 'ds-1:Market Analyst:Supply Chain Lead', response: null, error: null },
  { type: 'agent', index: 1, total: 2, profile: profile('Market Analyst', 'POSITIVE', [EXPANSION, EXPANSION_DISTRIBUTION, COMPETITORS]) },
  { type: 'agent', index: 2, total: 2, profile: profile('Supply Chain Lead', 'NEGATIVE', []) },
  {
    type: 'round',
    round: 1,
    pairs: [],
    turns: [
      turn('Market Analyst', 'POSITIVE', 0.82, 'Nordic capacity is underused.', ['Nordic capacity', 'Distribution capacity']),
      turn('Supply Chain Lead', 'NEGATIVE', 0.71, 'The Baltic routes are strained.', ['Nordic capacity', 'Distribution capacity']),
    ],
  },
  {
    type: 'commit',
    round: 1,
    opinions: 1,
    edges: 1,
    written_nodes: [{ key: 'ds-1:qh:1:Market Analyst', label: OPINION_TYPE, name: 'Market Analyst · pass 1' }],
    written_links: [{ from: 'ds-1:Market Analyst', to: 'ds-1:qh:1:Market Analyst', kind: 'STATED' }],
  },
  { type: 'round', round: 2, pairs: [], turns: [turn('Market Analyst', 'POSITIVE', 0.8, 'Capacity is the lever.', ['Nordic capacity'])] },
]

const run = fold(EVENTS)

const MATERIAL: GraphNode = { id: 'ds-1:Distribution capacity', label: 'Distribution capacity', type: 'Facility' }
/** Cited by one expert twice and another once — the passes read as words, deduplicated. */
const NORDIC: GraphNode = { id: 'ds-1:Nordic capacity', label: 'Nordic capacity', type: 'Facility' }
const SILENT_MATERIAL: GraphNode = { id: 'ds-1:Quiet entry', label: 'Quiet entry', type: 'Facility' }
const LONELY: GraphNode = { id: 'ds-1:Lonely', label: 'Lonely', type: 'Facility' }
const EXPERT: GraphNode = { id: 'ds-1:Market Analyst', label: 'Market Analyst', type: EXPERT_TYPE }
const OPINION: GraphNode = { id: 'ds-1:qh:1:Market Analyst', label: 'Market Analyst · pass 1', type: OPINION_TYPE }

const NODES: Record<string, GraphNode> = Object.fromEntries(
  [MATERIAL, NORDIC, SILENT_MATERIAL, LONELY, EXPERT, OPINION].map((node) => [node.id, node]),
)

const CONNECTION: GraphEdge = {
  source: 'ds-1:Market Analyst',
  target: 'ds-1:Distribution capacity',
  label: 'MENTIONS',
}
const EDGES: Record<string, GraphEdge> = { [`${CONNECTION.source}|${CONNECTION.target}|${CONNECTION.label}`]: CONNECTION }

const draw = (details: MapDetails) => renderToStaticMarkup(<NodeDetailsView details={details} onClose={() => {}} />)

const drawn = (node: GraphNode) => draw(entryDetails(run, node))

/** The markup of one section — from its heading to its close, so an assertion lands in one block. */
function sectionOf(html: string, heading: string): string {
  const at = html.indexOf(`>${heading}<`)
  if (at < 0) return ''
  return html.slice(at, html.indexOf('</section>', at))
}

describe('one entry, as the drawer reads it (§9.5)', () => {
  it('names every entry and says which kind it is, with the kind’s own glyph', () => {
    const material = entryDetails(run, MATERIAL)
    expect(material.name).toBe('Distribution capacity')
    expect(material.glyph).toBe('⊕')
    expect(material.kindLabel).toBe('an entry from your material')

    const expert = entryDetails(run, EXPERT)
    expect(expert.glyph).toBe('◉')
    expect(expert.kindLabel).toBe('an expert in your panel')

    const opinion = entryDetails(run, OPINION)
    expect(opinion.glyph).toBe('⊗')
    expect(opinion.kindLabel).toBe('an opinion held by Market Analyst')
  })

  it('reads an expert’s source material as document titles, one row per document', () => {
    expect(entryDetails(run, EXPERT).sources).toEqual([
      { title: 'European Expansion Analysis.pdf', where: ['Market outlook', 'Distribution'] },
      { title: 'competitor-research.md', where: [] },
    ])
  })

  it('never renders a chunk id — the FROM block is the material, not the internals', () => {
    expect(drawn(EXPERT)).not.toContain('chunk-1')
    expect(drawn(EXPERT)).not.toMatch(/\bchunks?\b/i)
  })

  it('says in words when an entry has no source material to name', () => {
    const material = sectionOf(drawn(MATERIAL), 'From')
    expect(material).toContain('No source documents were recorded for this entry.')
    expect(material).not.toContain('<li')

    expect(sectionOf(drawn(SILENT_MATERIAL), 'From')).toContain('No source documents were recorded for this entry.')
  })

  it('names every expert who cited the entry, and the passes they cited it in', () => {
    const cited = sectionOf(drawn(MATERIAL), 'Referenced by')
    expect(cited).toContain('Market Analyst')
    expect(cited).toContain('Supply Chain Lead')
    expect(cited.match(/pass 1</g)).toHaveLength(2) // both cited it in the first pass only
  })

  it('reads the passes of one expert across passes as one row, deduplicated', () => {
    const cited = sectionOf(drawn(NORDIC), 'Referenced by')
    expect(cited).toContain('pass 1, 2')
    expect(cited).toContain('pass 1<') // Supply Chain Lead cited it in the first pass only
  })

  it('says in words when no expert has cited the entry', () => {
    expect(entryDetails(run, LONELY).referencedBy).toEqual([])
    expect(sectionOf(drawn(LONELY), 'Referenced by')).toContain('No expert has cited this entry yet.')
  })

  it('reads a held opinion as its holder’s position in the pass it was filed', () => {
    expect(entryDetails(run, OPINION).held).toEqual({ stance: 'POSITIVE', confidence: 0.82, view: 'Nordic capacity is underused.' })
  })

  it('reads an expert’s position from the last pass they spoke in', () => {
    expect(entryDetails(run, EXPERT).held).toEqual({ stance: 'POSITIVE', confidence: 0.8, view: 'Capacity is the lever.' })
  })

  it('holds no position for the material itself', () => {
    expect(entryDetails(run, MATERIAL).held).toBe(null)
  })

  it('reads a connection as the two entries it joins, and its kind', () => {
    const details = resolveSelection(run, NODES, EDGES, { kind: 'connection', id: Object.keys(EDGES)[0] })
    expect(details).toEqual({
      kind: 'connection',
      name: 'Market Analyst —MENTIONS→ Distribution capacity',
      glyph: '—',
      kindLabel: 'a connection between two entries',
    })
  })

  it('resolves nothing for a selection the map no longer holds', () => {
    expect(resolveSelection(run, NODES, {}, { kind: 'entry', id: 'gone' })).toBe(null)
    expect(resolveSelection(run, NODES, {}, { kind: 'connection', id: 'gone' })).toBe(null)
  })
})

describe('the drawer’s panel (§9.5)', () => {
  it('draws its heading, its glyph, its kind and its two readings of the entry', () => {
    const html = drawn(MATERIAL)
    expect(html).toContain('Distribution capacity')
    expect(html).toContain('⊕')
    expect(html).toContain('an entry from your material')
    expect(html).toContain('>From<')
    expect(html).toContain('>Referenced by<')
  })

  it('shows the held view with the app’s stance rendering and its confidence figure', () => {
    const argued = sectionOf(drawn(OPINION), 'Argued as')
    expect(argued).toContain('POSITIVE')
    expect(argued).toContain('0.82')
    expect(argued).toContain('Nordic capacity is underused.')
  })

  it('carries no held view for an entry nobody has argued', () => {
    expect(drawn(MATERIAL)).not.toContain('>Argued as<')
  })

  it('states the passes in words a customer reads, never an internal identifier', () => {
    const html = drawn(NORDIC)
    expect(html).toContain('pass 1, 2')
    expect(html).not.toMatch(/\brounds?\b/i)
  })

  it('is a real modal dialog — the trap and the escape belong to the drawer it reuses', () => {
    const html = drawn(MATERIAL)
    expect(html).toContain('role="dialog"')
    expect(html).toContain('aria-modal="true"')
    expect(html).toContain('aria-label="Distribution capacity"')
    expect(html).toContain('Esc closes · focus returns to the map')
  })

  it('offers a labelled way out for a pointer, not only the escape key', () => {
    expect(drawn(MATERIAL)).toContain('aria-label="Close"')
  })
})

describe('opening an entry from the map', () => {
  beforeEach(() => useSelectionStore.setState({ selection: null }))

  // The channel, the resolution and the panel are asserted as a chain. The store-reading default
  // export cannot be rendered here at all: zustand v5 serves its INITIAL state as the snapshot a
  // server render reads, so `renderToStaticMarkup` can never observe a write to the store. That last
  // hop — subscribe and re-render — is React's own, and is stated as construction in the report.
  it('draws nothing while the customer has opened nothing', () => {
    expect(useSelectionStore.getState().selection).toBe(null)
  })

  it('draws the entry the map put in the channel, with the pass it was cited in', () => {
    useSelectionStore.getState().open({ kind: 'entry', id: MATERIAL.id })
    const selection = useSelectionStore.getState().selection!
    const html = draw(resolveSelection(run, NODES, EDGES, selection)!)
    expect(html).toContain('Distribution capacity')
    expect(html).toContain('an entry from your material')
    expect(html).toContain('Market Analyst')
  })

  it('draws nothing for a selection the map no longer holds — a stale selection is not a blank panel', () => {
    useSelectionStore.getState().open({ kind: 'entry', id: 'gone' })
    const selection = useSelectionStore.getState().selection!
    expect(resolveSelection(run, NODES, EDGES, selection)).toBe(null)
  })
})

describe('the copy law (§13) governs every string the drawer renders', () => {
  const BANNED =
    /\b(?:agents?|graphs?|nodes?|edges?|rounds?|retrieval|ontolog(?:y|ies)|models?|societ(?:y|ies)|chunks?|embeddings?|vectors?|llms?|prompts?|tokens?|pipelines?|jobs?)\b/i

  it('renders no banned word for any kind of entry', () => {
    for (const node of [MATERIAL, SILENT_MATERIAL, LONELY, EXPERT, OPINION]) {
      expect(drawn(node), node.label).not.toMatch(BANNED)
    }
  })

  it('renders no banned word for a connection', () => {
    expect(draw(resolveSelection(run, NODES, EDGES, { kind: 'connection', id: Object.keys(EDGES)[0] })!)).not.toMatch(BANNED)
  })
})
