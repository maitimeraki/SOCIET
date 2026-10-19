import { beforeEach, describe, expect, it, vi } from 'vitest'
import Graph from 'graphology'
import { renderToStaticMarkup } from 'react-dom/server'
import { useGraphStore } from '../../graph/graphStore'
import type { GraphEdge, GraphNode } from '../../graph/graphStore'
import { CORPUS_COLOR, EXPERT_COLOR, OPINION_TYPE, POSITION_COLORS, UNPOSITIONED_COLOR } from '../../graph/layers'
import {
  GraphLegend,
  MAX_ANIMATED_NODES,
  MAX_LABELLED_NODES,
  SIGMA_SETTINGS,
  TEXT_FALLBACK_LIMIT,
  drawNodeLabel,
  graphAriaLabel,
  graphStatusMessage,
  graphStreamPhase,
  graphTextFallback,
  seedPosition,
  showEdgeLabels,
  showNodeLabels,
  shouldAnimateLayout,
  simplifiedViewNotice,
  syncGraph,
} from './GraphCanvas'
// §13 — the one copy-law guard. The canvas binds WebGL under Node and cannot be rendered in tests,
// so its customer-visible copy is checked through the pure string helpers it renders from instead.
import { BANNED_WORD } from '../../test/copyLaw'

// No jsdom / no testing-library in this repo: the canvas is exercised through its
// pure sync function. React/Sigma never mount, so mock the one DOM-bound import.
vi.mock('@react-sigma/core', () => ({ SigmaContainer: () => null, useSigma: () => null }))

const byId = (...nodes: GraphNode[]): Record<string, GraphNode> =>
  Object.fromEntries(nodes.map((node) => [node.id, node]))

describe('SIGMA_SETTINGS', () => {
  it('allows the hidden container the minimised pane mounts, so the phone page cannot crash', () => {
    expect(SIGMA_SETTINGS.allowInvalidContainer).toBe(true)
  })
})

describe('syncGraph', () => {
  it('mirrors the store nodes and edges into the graphology instance', () => {
    const graph = new Graph({ multi: true })
    const nodes = byId(
      { id: 'a', label: 'Glucose', type: 'Molecule' },
      { id: 'b', label: 'Respiration', type: 'Process' },
    )
    const edges: Record<string, GraphEdge> = {
      'a|b|POWERS': { source: 'a', target: 'b', label: 'POWERS' },
    }

    syncGraph(graph, nodes, edges)

    expect(graph.order).toBe(2)
    expect(graph.size).toBe(1)
  })

  it('colours each entry by its kind — the material blue, an expert’s luminous white', () => {
    const graph = new Graph({ multi: true })
    const nodes = byId(
      { id: 'ds-1:steel tariffs', label: 'Steel tariffs', type: 'Topic' },
      { id: 'ds-1:D. Weber', label: 'D. Weber', type: 'Expert' },
    )

    syncGraph(graph, nodes, {})

    expect(graph.getNodeAttribute('ds-1:steel tariffs', 'color')).toBe(CORPUS_COLOR)
    expect(graph.getNodeAttribute('ds-1:D. Weber', 'color')).toBe(EXPERT_COLOR)
  })

  it('colours an opinion by the position the backend stored with it (§2.4)', () => {
    const graph = new Graph({ multi: true })
    const nodes = byId(
      { id: 'o+', label: '+', type: OPINION_TYPE, stance: 'POSITIVE' },
      { id: 'o-', label: '-', type: OPINION_TYPE, stance: 'NEGATIVE' },
    )

    syncGraph(graph, nodes, {})

    expect(graph.getNodeAttribute('o+', 'color')).toBe(POSITION_COLORS.POSITIVE)
    expect(graph.getNodeAttribute('o-', 'color')).toBe(POSITION_COLORS.NEGATIVE)
  })

  it('colours an opinion whose position is not recorded in the neutral fallback, never a position’s hue', () => {
    const graph = new Graph({ multi: true })
    syncGraph(graph, byId({ id: 'o', label: 'D. Weber · pass 1', type: OPINION_TYPE }), {})

    const color = graph.getNodeAttribute('o', 'color') as string
    expect(color).toBe(UNPOSITIONED_COLOR)
    expect(Object.values(POSITION_COLORS)).not.toContain(color)
  })

  it('keeps ONE node when a repeated id arrives', () => {
    const graph = new Graph({ multi: true })
    syncGraph(graph, byId({ id: 'a', label: 'Glucose', type: 'Molecule' }), {})
    syncGraph(graph, byId({ id: 'a', label: 'Glucose (revised)', type: 'Molecule' }), {})

    expect(graph.order).toBe(1)
    expect(graph.getNodeAttribute('a', 'label')).toBe('Glucose (revised)')
  })

  it('seeds every added node with a finite position so Sigma never sees a positionless node', () => {
    const graph = new Graph({ multi: true })
    const nodes = byId(
      { id: 'a', label: 'Glucose', type: 'Molecule' },
      { id: 'b', label: 'Respiration', type: 'Process' },
      { id: 'c', label: 'ATP', type: 'Molecule' },
    )

    syncGraph(graph, nodes, {})

    for (const id of ['a', 'b', 'c']) {
      expect(Number.isFinite(graph.getNodeAttribute(id, 'x'))).toBe(true)
      expect(Number.isFinite(graph.getNodeAttribute(id, 'y'))).toBe(true)
    }
  })

  it('keeps a node position once it has settled (a re-sync does not re-seed it)', () => {
    const graph = new Graph({ multi: true })
    syncGraph(graph, byId({ id: 'a', label: 'A', type: 'X' }), {})
    graph.setNodeAttribute('a', 'x', 42)

    syncGraph(graph, byId({ id: 'a', label: 'A', type: 'X' }), {})

    expect(graph.getNodeAttribute('a', 'x')).toBe(42)
  })

  it('drops nodes and edges the store no longer holds (snapshot reset)', () => {
    const graph = new Graph({ multi: true })
    const nodes = byId(
      { id: 'a', label: 'A', type: 'X' },
      { id: 'b', label: 'B', type: 'Y' },
    )
    syncGraph(graph, nodes, { 'a|b|R': { source: 'a', target: 'b', label: 'R' } })

    syncGraph(graph, byId({ id: 'b', label: 'B', type: 'Y' }), {})

    expect(graph.order).toBe(1)
    expect(graph.hasNode('a')).toBe(false)
    expect(graph.size).toBe(0)
  })

  it('keeps two edges linking the same nodes with different labels (multi graph)', () => {
    // Regression: edge identity is `source|target|label`, so two chunks routinely connect the
    // same pair with different labels. A SIMPLE graphology graph throws UsageGraphError on the
    // second addEdgeWithKey, which crashed the sync effect and blanked the page.
    const graph = new Graph({ multi: true })
    const nodes = byId(
      { id: 'a', label: 'Eu ai act', type: 'Regulation' },
      { id: 'b', label: 'Autonomous warehouse robotics', type: 'Technology' },
    )
    const edges: Record<string, GraphEdge> = {
      'a|b|CLASSIFIES_AS': { source: 'a', target: 'b', label: 'CLASSIFIES_AS' },
      'a|b|MANDATES': { source: 'a', target: 'b', label: 'MANDATES' },
    }

    expect(() => syncGraph(graph, nodes, edges)).not.toThrow()
    expect(graph.size).toBe(2)
    expect(graph.hasEdge('a|b|CLASSIFIES_AS')).toBe(true)
    expect(graph.hasEdge('a|b|MANDATES')).toBe(true)
  })
})

describe('large-graph guard', () => {
  it('animates the layout up to the ceiling and freezes it above', () => {
    expect(shouldAnimateLayout(300)).toBe(true)
    expect(shouldAnimateLayout(MAX_ANIMATED_NODES)).toBe(true)
    expect(shouldAnimateLayout(1600)).toBe(false)
  })

  it('shows node labels up to the label ceiling and hides them above', () => {
    expect(showNodeLabels(300)).toBe(true)
    expect(showNodeLabels(MAX_LABELLED_NODES)).toBe(true)
    expect(showNodeLabels(1600)).toBe(false)
  })

  it('shows edge labels up to the animation ceiling and hides them above', () => {
    expect(showEdgeLabels(300)).toBe(true)
    expect(showEdgeLabels(1600)).toBe(false)
  })

  it('offers the simplified-view notice only while degrading', () => {
    expect(simplifiedViewNotice(300)).toBeNull()
    expect(simplifiedViewNotice(1600)).toBe('showing simplified view (1600 entries)')
  })

  it('drops node labels from the graph attributes above the ceiling', () => {
    const graph = new Graph({ multi: true })
    const nodes: Record<string, GraphNode> = {}
    for (let i = 0; i < 1600; i++) nodes[`n${i}`] = { id: `n${i}`, label: `Node ${i}`, type: 'Thing' }

    syncGraph(graph, nodes, {})

    expect(graph.getNodeAttribute('n0', 'label')).toBeUndefined()
  })

  it('keeps node labels for a graph under the ceiling', () => {
    const graph = new Graph({ multi: true })
    const nodes = byId(
      { id: 'a', label: 'Glucose', type: 'Molecule' },
      { id: 'b', label: 'Respiration', type: 'Process' },
    )

    syncGraph(graph, nodes, {})

    expect(graph.getNodeAttribute('a', 'label')).toBe('Glucose')
  })

  it('never sets an edge label attribute — edge labels stay off', () => {
    const graph = new Graph({ multi: true })
    const nodes = byId(
      { id: 'a', label: 'Glucose', type: 'Molecule' },
      { id: 'b', label: 'ATP', type: 'Molecule' },
    )
    const edges: Record<string, GraphEdge> = { 'a|b|POWERS': { source: 'a', target: 'b', label: 'POWERS' } }

    syncGraph(graph, nodes, edges)

    expect(graph.getEdgeAttribute('a|b|POWERS', 'label')).toBeUndefined()
  })
})

describe('drawNodeLabel', () => {
  const data = { x: 10, y: 20, size: 7, label: 'Glucose', color: '#000' }

  it('strokes a halo before filling, so an edge cannot cut through the label text', () => {
    const calls: string[] = []
    const context = {
      font: '',
      lineJoin: '',
      lineWidth: 0,
      strokeStyle: '',
      fillStyle: '',
      strokeText: () => calls.push('stroke'),
      fillText: () => calls.push('fill'),
    }
    const settings = { labelSize: 12, labelFont: 'X', labelWeight: '500', labelColor: { color: '#111111' } }

    drawNodeLabel(context as unknown as CanvasRenderingContext2D, data as never, settings as never)

    expect(calls).toEqual(['stroke', 'fill'])
    expect(context.fillStyle).toBe('#111111')
  })

  it('draws nothing for a node without a label', () => {
    const calls: string[] = []
    const context = { strokeText: () => calls.push('stroke'), fillText: () => calls.push('fill') }
    const settings = { labelSize: 12, labelFont: 'X', labelWeight: '500', labelColor: { color: '#111111' } }

    drawNodeLabel(context as unknown as CanvasRenderingContext2D, { ...data, label: undefined } as never, settings as never)

    expect(calls).toEqual([])
  })
})

describe('seedPosition', () => {
  it('spreads successive nodes apart rather than stacking them at the origin', () => {
    const a = seedPosition(0)
    const b = seedPosition(1)
    expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeGreaterThan(0)
  })

  it('is deterministic for a given index', () => {
    expect(seedPosition(5)).toEqual(seedPosition(5))
  })
})

describe('graphAriaLabel', () => {
  it('counts the nodes, edges and entity types', () => {
    expect(graphAriaLabel(12, 8, 3)).toBe('Your map: 12 entries, 8 connections, 3 entity types')
  })

  it('pluralises a lone node, edge and entity type', () => {
    expect(graphAriaLabel(1, 1, 1)).toBe('Your map: 1 entry, 1 connection, 1 entity type')
  })

  it('reads as an empty graph before anything arrives', () => {
    expect(graphAriaLabel(0, 0, 0)).toBe('Your map: 0 entries, 0 connections, 0 entity types')
  })
})

describe('graphStreamPhase / graphStatusMessage', () => {
  it('waits for the first chunk while the graph is empty', () => {
    expect(graphStreamPhase(0, 'connecting', false)).toBe('waiting')
    expect(graphStreamPhase(0, 'open', false)).toBe('waiting')
    expect(graphStatusMessage(0, 'open', false)).toBe('Waiting for the first section…')
  })

  it('streams silently once a node has arrived', () => {
    expect(graphStreamPhase(3, 'open', false)).toBe('streaming')
    expect(graphStatusMessage(3, 'open', false)).toBeNull()
  })

  it('reports failure when the socket closes before done', () => {
    expect(graphStreamPhase(5, 'closed', false)).toBe('failed')
    expect(graphStatusMessage(5, 'closed', false)).toBe('The live map stream failed — the map stays as the last snapshot.')
  })

  it('reports the ended state on a done frame, even with zero nodes', () => {
    expect(graphStreamPhase(0, 'closed', true)).toBe('ended')
    expect(graphStatusMessage(0, 'closed', true)).toBe('The live map stream has ended.')
  })
})

describe('the copy law (§13) governs every string the canvas renders (§8.5 — WebGL-free)', () => {
  it('renders no banned word in the img label, the status overlay or the simplified-view notice', () => {
    const rendered = [
      graphAriaLabel(12, 8, 3),
      graphStatusMessage(0, 'open', false),
      graphStatusMessage(5, 'closed', false),
      graphStatusMessage(0, 'closed', true),
      simplifiedViewNotice(1600),
    ].filter((line): line is string => line !== null)
    expect(rendered).not.toHaveLength(0)
    for (const line of rendered) expect(line).not.toMatch(BANNED_WORD)
  })
})

describe('graphTextFallback', () => {
  const nodes: GraphNode[] = [
    { id: 'a', label: 'Glucose', type: 'Molecule' },
    { id: 'b', label: 'Respiration', type: 'Process' },
    { id: 'c', label: 'ATP', type: 'Molecule' },
  ]

  it('renders relations and standalone entities as text lines', () => {
    const edges: GraphEdge[] = [{ source: 'a', target: 'b', label: 'POWERS' }]

    const { lines, omitted } = graphTextFallback(nodes, edges, TEXT_FALLBACK_LIMIT)

    expect(lines).toEqual(['Glucose —POWERS→ Respiration', 'ATP (Molecule)'])
    expect(omitted).toBe(0)
  })

  it('caps the list at the limit and counts what it left out', () => {
    const edges: GraphEdge[] = [{ source: 'a', target: 'b', label: 'POWERS' }]

    const { lines, omitted } = graphTextFallback(nodes, edges, 1)

    expect(lines).toEqual(['Glucose —POWERS→ Respiration'])
    expect(omitted).toBe(1)
  })

  it('skips an edge whose endpoint is not in the store', () => {
    const edges: GraphEdge[] = [{ source: 'a', target: 'missing', label: 'POWERS' }]

    const { lines, omitted } = graphTextFallback(nodes, edges, TEXT_FALLBACK_LIMIT)

    expect(lines).toEqual(['Glucose (Molecule)', 'Respiration (Process)', 'ATP (Molecule)'])
    expect(omitted).toBe(0)
  })
})

describe('GraphLegend — the map’s key (§6, §9)', () => {
  it('names every colour the map draws, each with its own word', () => {
    const html = renderToStaticMarkup(<GraphLegend hasEntries />)

    for (const word of ['Corpus', 'Experts', 'POSITIVE', 'NEUTRAL', 'AMBIVALENT', 'NEGATIVE', 'No position']) {
      expect(html).toContain(word)
    }
    // The swatches carry the very hues the canvas paints, so the key and the map cannot drift.
    for (const color of [CORPUS_COLOR, EXPERT_COLOR, UNPOSITIONED_COLOR, ...Object.values(POSITION_COLORS)]) {
      expect(html).toContain(color)
    }
  })

  it('draws nothing over a map holding no entry', () => {
    expect(renderToStaticMarkup(<GraphLegend hasEntries={false} />)).toBe('')
  })
})

// One store fed by two streams (D14): the corpus layer folds in from the graph stream, the expert
// and opinion layers fold in from the debate stream. The store is a module singleton — reset it
// between cases so counts are absolute.
describe('the one map, fed by both streams', () => {
  beforeEach(() => useGraphStore.setState({ nodes: {}, edges: {}, labels: [], version: 0 }))

  it('an agent event seats exactly one entry, keyed as the backend keys the person', () => {
    useGraphStore.getState().mergeExpert({ datasetId: 'ds-1', name: 'D. Weber' })

    expect(Object.keys(useGraphStore.getState().nodes)).toEqual(['ds-1:D. Weber'])
  })

  it('a commit seats one entry per written node and one connection per written link, keyed as the backend keyed them', () => {
    useGraphStore.getState().mergeOpinions(
      [
        { key: 'ds-1:qh:1:D. Weber', label: 'Opinion', name: 'D. Weber · pass 1' },
        { key: 'ds-1:qh:1:M. Chen', label: 'Opinion', name: 'M. Chen · pass 1' },
      ],
      [
        { from: 'ds-1:D. Weber', to: 'ds-1:qh:1:D. Weber', kind: 'STATED' },
        { from: 'ds-1:M. Chen', to: 'ds-1:qh:1:M. Chen', kind: 'STATED' },
      ],
    )

    const { nodes, edges } = useGraphStore.getState()
    expect([Object.keys(nodes), Object.keys(edges)]).toEqual([
      ['ds-1:qh:1:D. Weber', 'ds-1:qh:1:M. Chen'],
      ['ds-1:D. Weber|ds-1:qh:1:D. Weber|STATED', 'ds-1:M. Chen|ds-1:qh:1:M. Chen|STATED'],
    ])
  })

  it('keeps a written entry verbatim — its name is the label, its kind the type', () => {
    useGraphStore.getState().mergeOpinions(
      [{ key: 'ds-1:qh:1:D. Weber', label: 'Opinion', name: 'D. Weber · pass 1' }],
      [],
    )

    const node = useGraphStore.getState().nodes['ds-1:qh:1:D. Weber']
    expect([node.label, node.type]).toEqual(['D. Weber · pass 1', 'Opinion'])
  })

  it('folding the same commit twice adds nothing the second time', () => {
    const nodes = [{ key: 'ds-1:qh:1:D. Weber', label: 'Opinion', name: 'D. Weber · pass 1' }]
    const links = [{ from: 'ds-1:D. Weber', to: 'ds-1:qh:1:D. Weber', kind: 'STATED' }]

    useGraphStore.getState().mergeOpinions(nodes, links)
    useGraphStore.getState().mergeOpinions(nodes, links)

    const { nodes: after, edges: afterEdges } = useGraphStore.getState()
    expect([Object.keys(after).length, Object.keys(afterEdges).length]).toEqual([1, 1])
  })

  it('the corpus layer and the expert layer share the one store, neither clearing the other', () => {
    useGraphStore.getState().mergeDelta({ nodes: [{ id: 'ds-1:steel tariffs', label: 'steel tariffs', type: 'Topic' }], edges: [] })
    useGraphStore.getState().mergeExpert({ datasetId: 'ds-1', name: 'D. Weber' })

    expect(Object.keys(useGraphStore.getState().nodes).sort()).toEqual(['ds-1:D. Weber', 'ds-1:steel tariffs'])
  })
})
