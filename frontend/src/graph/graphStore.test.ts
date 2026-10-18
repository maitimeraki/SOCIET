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

  it('mergeVocabulary adds a label once and keeps its place on a second call', () => {
    const { mergeVocabulary } = useGraphStore.getState()
    mergeVocabulary(['Molecule'])
    expect(useGraphStore.getState().labels).toEqual(['Molecule'])

    mergeVocabulary(['Molecule', 'Process'])
    expect(useGraphStore.getState().labels).toEqual(['Molecule', 'Process'])
  })

  it('mergeOpinions seats the position the caller resolved for an entry, and none when it resolved none', () => {
    const { mergeOpinions } = useGraphStore.getState()
    mergeOpinions(
      [
        { key: 'ds-1:qh:1:D. Weber', label: 'Opinion', name: 'D. Weber · pass 1' },
        { key: 'ds-1:qh:1:M. Chen', label: 'Opinion', name: 'M. Chen · pass 1' },
      ],
      [],
      { 'ds-1:qh:1:D. Weber': 'POSITIVE' },
    )

    const { nodes } = useGraphStore.getState()
    expect(nodes['ds-1:qh:1:D. Weber'].stance).toBe('POSITIVE')
    expect(nodes['ds-1:qh:1:M. Chen'].stance).toBeUndefined()
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
    expect(state.labels).toEqual(['Y'])
  })
})

describe('the vocabulary — the entity types the map holds', () => {
  it('keeps the labels in first-seen order, deduped, whatever the arrival order', () => {
    const { mergeVocabulary } = useGraphStore.getState()
    mergeVocabulary(['Company', 'Market', 'Regulation'])
    mergeVocabulary(['Regulation', 'Company'])

    expect(useGraphStore.getState().labels).toEqual(['Company', 'Market', 'Regulation'])
  })

  it('replaces the vocabulary on a snapshot reset, so no previous read’s types linger', () => {
    const { mergeVocabulary, applySnapshot } = useGraphStore.getState()
    mergeVocabulary(['Company'])
    applySnapshot({ nodes: [], edges: [], labels: ['Regulation', 'Market'] })

    expect(useGraphStore.getState().labels).toEqual(['Regulation', 'Market'])
  })
})
