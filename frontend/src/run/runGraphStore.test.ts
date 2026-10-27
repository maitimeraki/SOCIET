import { describe, expect, it } from 'vitest'
import { EXPERT_TYPE } from '../graph/graphStore'
import type { GraphSnapshot } from '../graph/graphStore'
import type { AgentProfile, RunEvent, WrittenNode } from './events'
import { fold } from './reducer'
import { composeRunGraph } from './runGraphStore'

const NOW = () => 1_000

/** An `agent` event seating one expert, carrying the dataset id the backend keys the stored person under. */
const agent = (name: string, datasetId = 'ds-1'): RunEvent => {
  const profile: AgentProfile = {
    agent_id: name,
    identity: { name, archetype: 'analyst', communication_style: 'measured' },
    bio: '',
    detailed_perspective: '',
    stance: 'NEUTRAL',
    intensity: 0.5,
    confidence: 0.5,
    conviction: 0.5,
    cior: 0,
    domain_tags: [],
    communication_radius: 1,
    summary_provenance: [],
    confidence_breakdown: { source_breadth: 0, node_density: 0, relationship_connectivity: 0 },
    graph_snapshot: { dataset_id: datasetId, chunk_count: 1, version_hash: 'v1' },
  }
  return { type: 'agent', index: 1, total: 1, profile }
}

/** The corpus read (Task 1.3) — the entries extraction wrote, as the snapshot frame frames them. */
const CORPUS: GraphSnapshot = {
  nodes: [
    { id: 'EU', label: 'EU', type: 'Region' },
    { id: 'steel tariffs', label: 'Steel tariffs', type: 'Topic' },
    { id: 'EuroSteel', label: 'EuroSteel', type: 'Company' },
  ],
  edges: [{ source: 'EuroSteel', target: 'EU', label: 'OPERATES_IN' }],
  labels: ['Company', 'Region', 'Topic'],
}

/** Composed entries counted by their kind — the entry's `type`, as the map holds it. */
const countsByType = (graph: ReturnType<typeof composeRunGraph>): Record<string, number> => {
  const counts: Record<string, number> = {}
  graph.forEachNode((_id, attributes) => {
    const type = attributes.type as string
    counts[type] = (counts[type] ?? 0) + 1
  })
  return counts
}

describe('composeRunGraph', () => {
  it('seats the corpus layer and one expert per agent', () => {
    const state = fold([agent('D. Weber'), agent('M. Chen')], NOW)
    // The expert kind is the live store's own — read from it, so the composer cannot drift from the map's colouring.
    expect(countsByType(composeRunGraph(state, CORPUS))).toEqual({ Region: 1, Topic: 1, Company: 1, [EXPERT_TYPE]: 2 })
  })

  it("adds a commit payload's written entries with their written connections", () => {
    const state = fold(
      [
        agent('D. Weber'),
        {
          type: 'commit',
          round: 1,
          opinions: 1,
          edges: 1,
          written_nodes: [{ key: 'ds-1:qh:1:D. Weber', label: 'Opinion', name: 'D. Weber · pass 1' }],
          written_links: [{ from: 'ds-1:D. Weber', to: 'ds-1:qh:1:D. Weber', kind: 'STATED' }],
        },
      ],
      NOW,
    )
    const graph = composeRunGraph(state, null)
    expect({
      nodes: graph.nodes().sort(),
      edges: graph.edges().map((key) => [graph.source(key), graph.target(key), graph.getEdgeAttribute(key, 'label')]),
    }).toEqual({
      nodes: ['ds-1:D. Weber', 'ds-1:qh:1:D. Weber'],
      edges: [['ds-1:D. Weber', 'ds-1:qh:1:D. Weber', 'STATED']],
    })
  })

  it('aggregates an entry written in two passes rather than duplicating it', () => {
    const written: WrittenNode = { key: 'ds-1:qh:1:D. Weber', label: 'Opinion', name: 'D. Weber · pass 1' }
    const commit = (round: number): RunEvent => ({
      type: 'commit',
      round,
      opinions: 1,
      edges: 0,
      written_nodes: [written],
      written_links: [],
    })
    const graph = composeRunGraph(fold([commit(1), commit(2)], NOW), null)
    expect(graph.order).toBe(1)
  })

  it('composes an identical graph from the same run folded twice (replay = live)', () => {
    const events: RunEvent[] = [
      agent('D. Weber'),
      agent('M. Chen'),
      {
        type: 'commit',
        round: 1,
        opinions: 1,
        edges: 1,
        written_nodes: [{ key: 'ds-1:qh:1:D. Weber', label: 'Opinion', name: 'D. Weber · pass 1' }],
        written_links: [{ from: 'ds-1:D. Weber', to: 'ds-1:qh:1:D. Weber', kind: 'STATED' }],
      },
    ]
    const first = composeRunGraph(fold(events, NOW), CORPUS).export()
    const second = composeRunGraph(fold(events, NOW), CORPUS).export()
    expect(first).toEqual(second)
  })

  it('seats each opinion with the position the pass recorded for its holder (§9.2)', () => {
    const state = fold(
      [
        agent('D. Weber'),
        {
          type: 'round',
          round: 1,
          pairs: [],
          turns: [{ agent_id: 'D. Weber', agent_name: 'D. Weber', content: 'yes', stance: 'POSITIVE', confidence: 0.8, references: [] }],
        },
        {
          type: 'commit',
          round: 1,
          opinions: 1,
          edges: 1,
          written_nodes: [{ key: 'ds-1:qh:1:D. Weber', label: 'Opinion', name: 'D. Weber · pass 1' }],
          written_links: [{ from: 'ds-1:D. Weber', to: 'ds-1:qh:1:D. Weber', kind: 'STATED' }],
        },
      ],
      NOW,
    )

    // The position the backend stores with an opinion is the holder's LAST turn in the pass.
    expect(composeRunGraph(state, null).getNodeAttribute('ds-1:qh:1:D. Weber', 'stance')).toBe('POSITIVE')
  })

  it('leaves the position unseated when the stored events carry no turn for the holder — never a guess', () => {
    const state = fold(
      [
        {
          type: 'commit',
          round: 1,
          opinions: 1,
          edges: 1,
          written_nodes: [{ key: 'ds-1:qh:1:D. Weber', label: 'Opinion', name: 'D. Weber · pass 1' }],
          written_links: [{ from: 'ds-1:D. Weber', to: 'ds-1:qh:1:D. Weber', kind: 'STATED' }],
        },
      ],
      NOW,
    )

    expect(composeRunGraph(state, null).getNodeAttribute('ds-1:qh:1:D. Weber', 'stance')).toBeUndefined()
  })

  it('includes only commits up to the selected pass', () => {
    const commit = (round: number): RunEvent => ({
      type: 'commit',
      round,
      opinions: 1,
      edges: 1,
      written_nodes: [{ key: `ds-1:qh:${round}:D. Weber`, label: 'Opinion', name: `D. Weber · pass ${round}` }],
      written_links: [{ from: 'ds-1:D. Weber', to: `ds-1:qh:${round}:D. Weber`, kind: 'STATED' }],
    })
    const state = fold([agent('D. Weber'), commit(1), commit(2)], NOW)

    const all = composeRunGraph(state, null)
    const round1 = composeRunGraph(state, null, 1)

    expect(round1.order).toBeLessThan(all.order)
    expect(round1.nodes()).toContain('ds-1:qh:1:D. Weber')
    expect(round1.nodes()).not.toContain('ds-1:qh:2:D. Weber')
    // The pass-2 connection goes with its pass — the filter drops edges as well as entries.
    expect(all.hasEdge('ds-1:D. Weber', 'ds-1:qh:2:D. Weber')).toBe(true)
    expect(round1.hasEdge('ds-1:D. Weber', 'ds-1:qh:2:D. Weber')).toBe(false)
  })

  it('leaves the corpus layer intact when replaying a pass', () => {
    const state = fold(
      [
        agent('D. Weber'),
        {
          type: 'commit',
          round: 2,
          opinions: 1,
          edges: 1,
          written_nodes: [{ key: 'ds-1:qh:2:D. Weber', label: 'Opinion', name: 'D. Weber · pass 2' }],
          written_links: [{ from: 'ds-1:D. Weber', to: 'ds-1:qh:2:D. Weber', kind: 'STATED' }],
        },
      ],
      NOW,
    )
    const round1 = composeRunGraph(state, CORPUS, 1)

    expect(countsByType(round1)).toEqual({ Region: 1, Topic: 1, Company: 1, [EXPERT_TYPE]: 1 })
    expect(round1.hasNode('EuroSteel')).toBe(true)
    expect(round1.hasEdge('EuroSteel', 'EU')).toBe(true)
    expect(round1.nodes()).not.toContain('ds-1:qh:2:D. Weber')
  })

  it('keeps an entry of an unknown kind rather than dropping it', () => {
    const state = fold(
      [
        {
          type: 'commit',
          round: 1,
          opinions: 1,
          edges: 0,
          written_nodes: [{ key: 'ds-1:widget:1', label: 'Widget', name: 'A widget' }],
        },
      ],
      NOW,
    )
    expect(composeRunGraph(state, null).getNodeAttribute('ds-1:widget:1', 'type')).toBe('Widget')
  })
})
