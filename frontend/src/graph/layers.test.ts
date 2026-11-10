import { describe, expect, it } from 'vitest'
import { EXPERT_TYPE } from './graphStore'
import type { GraphEdge, GraphNode } from './graphStore'
import { CORPUS_COLOR, EXPERT_COLOR, OPINION_TYPE, POSITION_COLORS, UNPOSITIONED_COLOR, entryColor, nodeLayer, visibleSlice, type LayerName } from './layers'
import type { Stance } from '../run/events'

// The layer filter's drop-branch, asserted on its own: `nodeLayer`'s mapping and the two ways
// `visibleSlice` narrows the store. The pane's tests drive the *toggle UI*; these drive what the
// toggles actually do — the one behaviour a regression could break while every UI test stays green.

const corpus: GraphNode = { id: 'ds-1:steel tariffs', label: 'steel tariffs', type: 'Topic' }
const expert: GraphNode = { id: 'ds-1:D. Weber', label: 'D. Weber', type: EXPERT_TYPE }
const opinion: GraphNode = { id: 'ds-1:qh:1:D. Weber', label: 'D. Weber · pass 1', type: OPINION_TYPE }

const nodes: Record<string, GraphNode> = { [corpus.id]: corpus, [expert.id]: expert, [opinion.id]: opinion }
const edges: Record<string, GraphEdge> = {
  'ds-1:steel tariffs|ds-1:steel tariffs|RELATES': { source: corpus.id, target: corpus.id, label: 'RELATES' },
  'ds-1:D. Weber|ds-1:qh:1:D. Weber|STATED': { source: expert.id, target: opinion.id, label: 'STATED' },
}

const showing = (...layers: LayerName[]): ReadonlySet<LayerName> => new Set<LayerName>(layers)

describe('nodeLayer — which layer an entry belongs to', () => {
  it('reads an expert entry as the expert layer', () => {
    expect(nodeLayer({ id: 'e', label: 'D. Weber', type: EXPERT_TYPE })).toBe('experts')
  })

  it('reads an opinion entry as the opinion layer', () => {
    expect(nodeLayer({ id: 'o', label: 'D. Weber · pass 1', type: OPINION_TYPE })).toBe('opinions')
  })

  it('reads a material entry as the corpus layer', () => {
    expect(nodeLayer(corpus)).toBe('corpus')
  })

  it('reads a kind it does not know as material — kept, never dropped', () => {
    expect(nodeLayer({ id: 'ds-1:widget:1', label: 'A widget', type: 'Widget' })).toBe('corpus')
  })
})

describe('entryColor — an entry’s colour, by kind and by position (§2.4, §9.2)', () => {
  it('draws the material in its own blue', () => {
    expect(entryColor(corpus)).toBe('#3B82F6')
    expect(CORPUS_COLOR).toBe('#3B82F6')
  })

  it('draws an expert in the luminous white', () => {
    expect(entryColor(expert)).toBe('#E2E8F0')
    expect(EXPERT_COLOR).toBe('#E2E8F0')
  })

  it('draws an opinion in its own position’s colour', () => {
    const positions: Stance[] = ['POSITIVE', 'NEUTRAL', 'AMBIVALENT', 'NEGATIVE']
    for (const stance of positions) expect(entryColor({ ...opinion, stance })).toBe(POSITION_COLORS[stance])
  })

  it('draws an opinion whose position the stored events do not carry in the neutral fallback, never a position’s hue', () => {
    const color = entryColor(opinion) // no stance seated
    expect(color).toBe(UNPOSITIONED_COLOR)
    expect(Object.values(POSITION_COLORS)).not.toContain(color)
  })

  it('names the four positions with the spec’s own colours (§2.4)', () => {
    expect(POSITION_COLORS).toEqual({ POSITIVE: '#4ADE80', NEUTRAL: '#94A3B8', AMBIVALENT: '#FBBF24', NEGATIVE: '#F87171' })
  })
})

describe('visibleSlice — the layers the canvas may draw', () => {
  it('drops the entries of a hidden layer and keeps the rest', () => {
    const slice = visibleSlice(nodes, edges, showing('experts', 'opinions', 'connections'))

    expect(Object.keys(slice.nodes).sort()).toEqual([expert.id, opinion.id].sort())
  })

  it('leaves the connections alone while the connections layer is on', () => {
    const slice = visibleSlice(nodes, edges, showing('experts', 'opinions', 'connections'))

    expect(slice.edges).toBe(edges)
  })

  it('empties the connections when the connections layer is off, dropping no entry', () => {
    const slice = visibleSlice(nodes, edges, showing('corpus', 'experts', 'opinions'))

    expect(slice.edges).toEqual({})
    expect(Object.keys(slice.nodes).sort()).toEqual(Object.keys(nodes).sort())
  })

  it('copies no entry — every surviving entry is the store’s own object', () => {
    const slice = visibleSlice(nodes, edges, showing('experts', 'opinions'))

    for (const id of [expert.id, opinion.id]) expect(slice.nodes[id]).toBe(nodes[id])
  })

  it('hands the store’s own maps straight back while every layer is on', () => {
    const slice = visibleSlice(nodes, edges, showing('corpus', 'experts', 'opinions', 'connections'))

    expect(slice.nodes).toBe(nodes)
    expect(slice.edges).toBe(edges)
  })

  it('hands the entry map back untouched when only the connections are off (F32)', () => {
    // Hiding the connections must not rebuild the entry map on every delta: with every ENTRY layer
    // still on, the slice passes the store's own map through, so only the connections are narrowed.
    const slice = visibleSlice(nodes, edges, showing('corpus', 'experts', 'opinions'))

    expect(slice.nodes).toBe(nodes)
    expect(slice.edges).toEqual({})
  })
})
