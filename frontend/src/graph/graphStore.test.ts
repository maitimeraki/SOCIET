import { beforeEach, describe, expect, it } from 'vitest'
import { LABEL_PALETTE, labelColor, useGraphStore } from './graphStore'

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

describe('label palette', () => {
  it('emits hex colours Sigma can parse (never hsl)', () => {
    for (const color of LABEL_PALETTE) expect(color).toMatch(/^#[0-9a-f]{6}$/i)
  })

  it('assigns a distinct colour to each of the first seven labels', () => {
    const colors = LABEL_PALETTE.map((_, index) => labelColor(index))
    expect(new Set(colors).size).toBe(LABEL_PALETTE.length)
  })

  it('gives the same set the same colours whatever the arrival order', () => {
    const { mergeVocabulary } = useGraphStore.getState()
    mergeVocabulary(['Company', 'Market', 'Regulation'])
    const first = Object.fromEntries(useGraphStore.getState().labels.map((l) => [l.label, l.color]))

    useGraphStore.setState({ labels: [] })
    mergeVocabulary(['Regulation', 'Company', 'Market'])
    const second = Object.fromEntries(useGraphStore.getState().labels.map((l) => [l.label, l.color]))

    expect(second).toEqual(first)
  })

  it('preserves each label colour across an applySnapshot that reorders the same labels', () => {
    const { applySnapshot } = useGraphStore.getState()
    applySnapshot({ nodes: [], edges: [], labels: ['Company', 'Market', 'Regulation'] })
    const first = Object.fromEntries(useGraphStore.getState().labels.map((l) => [l.label, l.color]))

    applySnapshot({ nodes: [], edges: [], labels: ['Regulation', 'Company', 'Market'] })
    const second = Object.fromEntries(useGraphStore.getState().labels.map((l) => [l.label, l.color]))

    expect(second).toEqual(first)
  })

  it('gives a promoted seventh label a colour unlike the existing six', () => {
    const { mergeVocabulary } = useGraphStore.getState()
    mergeVocabulary(['Company', 'Market', 'Regulation', 'Person', 'Product', 'Location'])
    mergeVocabulary(['RelationType'])

    const colors = useGraphStore.getState().labels.map((l) => l.color)
    expect(colors).toHaveLength(7)
    expect(new Set(colors).size).toBe(7)
  })
})
