import { beforeEach, describe, expect, it } from 'vitest'
import { useSelectionStore } from './selectionStore'

describe('the map’s selection channel', () => {
  beforeEach(() => useSelectionStore.setState({ selection: null }))

  it('holds nothing until the customer opens something', () => {
    expect(useSelectionStore.getState().selection).toBe(null)
  })

  it('holds the entry a click named', () => {
    useSelectionStore.getState().open({ kind: 'entry', id: 'ds-1:Nordic capacity' })
    expect(useSelectionStore.getState().selection).toEqual({ kind: 'entry', id: 'ds-1:Nordic capacity' })
  })

  it('holds a connection the same way', () => {
    useSelectionStore.getState().open({ kind: 'connection', id: 'a|b|MENTIONS' })
    expect(useSelectionStore.getState().selection).toEqual({ kind: 'connection', id: 'a|b|MENTIONS' })
  })

  it('replaces what was open — one entry’s details at a time', () => {
    useSelectionStore.getState().open({ kind: 'entry', id: 'one' })
    useSelectionStore.getState().open({ kind: 'entry', id: 'two' })
    expect(useSelectionStore.getState().selection).toEqual({ kind: 'entry', id: 'two' })
  })

  it('closes back to nothing', () => {
    useSelectionStore.getState().open({ kind: 'entry', id: 'one' })
    useSelectionStore.getState().close()
    expect(useSelectionStore.getState().selection).toBe(null)
  })
})
