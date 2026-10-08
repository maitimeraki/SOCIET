import { describe, expect, it, vi } from 'vitest'
import Graph from 'graphology'
import type { GraphEdge, GraphLabel, GraphNode } from '../../graph/graphStore'
import {
  MAX_ANIMATED_NODES,
  MAX_LABELLED_NODES,
  showEdgeLabels,
  showNodeLabels,
  shouldAnimateLayout,
  simplifiedViewNotice,
  syncGraph,
} from './GraphCanvas'

// No jsdom / no testing-library in this repo: the canvas is exercised through its
// pure sync function. React/Sigma never mount, so mock the one DOM-bound import.
vi.mock('@react-sigma/core', () => ({ SigmaContainer: () => null }))

const byId = (...nodes: GraphNode[]): Record<string, GraphNode> =>
  Object.fromEntries(nodes.map((node) => [node.id, node]))

describe('syncGraph', () => {
  it('mirrors the store nodes and edges into the graphology instance', () => {
    const graph = new Graph()
    const nodes = byId(
      { id: 'a', label: 'Glucose', type: 'Molecule' },
      { id: 'b', label: 'Respiration', type: 'Process' },
    )
    const edges: Record<string, GraphEdge> = {
      'a|b|POWERS': { source: 'a', target: 'b', label: 'POWERS' },
    }

    syncGraph(graph, nodes, edges, [])

    expect(graph.order).toBe(2)
    expect(graph.size).toBe(1)
  })

  it('colours a node from its promoted label colour', () => {
    const graph = new Graph()
    const labels: GraphLabel[] = [
      { label: 'Molecule', color: 'hsl(210 70% 55%)' },
      { label: 'Process', color: 'hsl(20 70% 55%)' },
    ]

    syncGraph(graph, byId({ id: 'a', label: 'Glucose', type: 'Molecule' }), {}, labels)

    expect(graph.getNodeAttribute('a', 'color')).toBe('hsl(210 70% 55%)')
  })

  it('keeps ONE node when a repeated id arrives', () => {
    const graph = new Graph()
    syncGraph(graph, byId({ id: 'a', label: 'Glucose', type: 'Molecule' }), {}, [])
    syncGraph(graph, byId({ id: 'a', label: 'Glucose (revised)', type: 'Molecule' }), {}, [])

    expect(graph.order).toBe(1)
    expect(graph.getNodeAttribute('a', 'label')).toBe('Glucose (revised)')
  })

  it('drops nodes and edges the store no longer holds (snapshot reset)', () => {
    const graph = new Graph()
    const nodes = byId(
      { id: 'a', label: 'A', type: 'X' },
      { id: 'b', label: 'B', type: 'Y' },
    )
    syncGraph(graph, nodes, { 'a|b|R': { source: 'a', target: 'b', label: 'R' } }, [])

    syncGraph(graph, byId({ id: 'b', label: 'B', type: 'Y' }), {}, [])

    expect(graph.order).toBe(1)
    expect(graph.hasNode('a')).toBe(false)
    expect(graph.size).toBe(0)
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
    expect(simplifiedViewNotice(1600)).toBe('showing simplified view (1600 nodes)')
  })

  it('drops node and edge labels from the graph attributes above the ceiling', () => {
    const graph = new Graph()
    const nodes: Record<string, GraphNode> = {}
    for (let i = 0; i < 1600; i++) nodes[`n${i}`] = { id: `n${i}`, label: `Node ${i}`, type: 'Thing' }
    const edges: Record<string, GraphEdge> = { 'n0|n1|REL': { source: 'n0', target: 'n1', label: 'REL' } }

    syncGraph(graph, nodes, edges, [])

    expect(graph.getNodeAttribute('n0', 'label')).toBeUndefined()
    expect(graph.getEdgeAttribute('n0|n1|REL', 'label')).toBeUndefined()
  })

  it('keeps node and edge labels for a graph under the ceilings', () => {
    const graph = new Graph()
    const nodes = byId(
      { id: 'a', label: 'Glucose', type: 'Molecule' },
      { id: 'b', label: 'Respiration', type: 'Process' },
    )
    const edges: Record<string, GraphEdge> = { 'a|b|POWERS': { source: 'a', target: 'b', label: 'POWERS' } }

    syncGraph(graph, nodes, edges, [])

    expect(graph.getNodeAttribute('a', 'label')).toBe('Glucose')
    expect(graph.getEdgeAttribute('a|b|POWERS', 'label')).toBe('POWERS')
  })
})
