import { beforeEach, describe, expect, it } from 'vitest'
import { useGraphStore } from './graphStore'

// The store is a module singleton — reset it between cases so counts are absolute.
beforeEach(() => useGraphStore.setState({ nodes: {}, edges: {}, labels: [] }))

describe('useGraphStore', () => {
  it('an overlapping node id yields ONE node', () => {
    const { mergeDelta } = useGraphStore.getState()
    mergeDelta({ nodes: [{ id: 'e1', label: 'Glucose', type: 'Molecule' }], edges: [] })
    mergeDelta({ nodes: [{ id: 'e1', label: 'Glucose (revised)', type: 'Molecule' }], edges: [] })

    const nodes = Object.values(useGraphStore.getState().nodes)
    expect(nodes).toHaveLength(1)
    expect(nodes[0].label).toBe('Glucose (revised)')
  })

  it('a duplicate edge key yields ONE edge', () => {
    const { mergeDelta } = useGraphStore.getState()
    const edge = { source: 'a', target: 'b', label: 'BINDS' }
    mergeDelta({ nodes: [], edges: [edge] })
    mergeDelta({ nodes: [], edges: [edge] })

    expect(Object.values(useGraphStore.getState().edges)).toHaveLength(1)
  })

  it('mergeVocabulary adds a label once and keeps its colour on a second call', () => {
    const { mergeVocabulary } = useGraphStore.getState()
    mergeVocabulary(['Molecule'])
    const first = useGraphStore.getState().labels
    expect(first).toHaveLength(1)
    expect(first[0].label).toBe('Molecule')

    mergeVocabulary(['Molecule'])
    const second = useGraphStore.getState().labels
    expect(second).toHaveLength(1)
    expect(second[0].color).toBe(first[0].color)
  })

  it('applySnapshot replaces the graph as a reconnect reset', () => {
    const { mergeDelta, mergeVocabulary, applySnapshot } = useGraphStore.getState()
    mergeDelta({ nodes: [{ id: 'old', label: 'Old', type: 'X' }], edges: [] })
    mergeVocabulary(['X'])

    applySnapshot({
      nodes: [{ id: 'new', label: 'New', type: 'Y' }],
      edges: [{ source: 'new', target: 'new', label: 'SELF' }],
      labels: ['Y'],
    })

    const state = useGraphStore.getState()
    expect(Object.keys(state.nodes)).toEqual(['new'])
    expect(Object.values(state.edges)).toHaveLength(1)
    expect(state.labels.map((l) => l.label)).toEqual(['Y'])
  })
})
