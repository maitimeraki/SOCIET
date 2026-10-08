import { describe, expect, it, vi } from 'vitest'
import Graph from 'graphology'
import type { GraphEdge, GraphLabel, GraphNode } from '../../graph/graphStore'
import { syncGraph } from './GraphCanvas'

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
