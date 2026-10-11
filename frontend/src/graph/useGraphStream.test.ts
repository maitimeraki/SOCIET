import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { connectGraphStream } from '../api/ws'
import { useGraphStore } from './graphStore'
import { routeGraphFrame } from './useGraphStream'
import type { GraphFrame } from './useGraphStream'

// The store is a module singleton — reset it between cases so counts are absolute.
beforeEach(() => useGraphStore.setState({ nodes: {}, edges: {}, labels: [] }))

const node = (id: string) => ({ id, label: id, type: 'Molecule' })
const nodes = () => Object.keys(useGraphStore.getState().nodes)

describe('routeGraphFrame', () => {
  it('snapshot resets the store, dropping anything merged before it', () => {
    useGraphStore.getState().mergeDelta({ nodes: [node('old')], edges: [] })
    routeGraphFrame({ type: 'snapshot', nodes: [node('new')], edges: [], labels: ['Molecule'] })
    expect(nodes()).toEqual(['new'])
  })

  it('delta merges into the store', () => {
    routeGraphFrame({ type: 'delta', nodes: [node('e1')], edges: [] })
    routeGraphFrame({ type: 'delta', nodes: [node('e2')], edges: [] })
    expect(nodes()).toEqual(['e1', 'e2'])
  })

  it('vocabulary adds labels to the store', () => {
    routeGraphFrame({ type: 'vocabulary', labels: ['Molecule', 'Process'] })
    expect(useGraphStore.getState().labels.map((l) => l.label)).toEqual(['Molecule', 'Process'])
  })

  it('an error frame surfaces its message but never merges as graph data', () => {
    const error = routeGraphFrame({ type: 'error', chunk_id: 'c9', message: 'chunk failed' })
    expect(error).toEqual({ chunk_id: 'c9', message: 'chunk failed' })
    expect(nodes()).toHaveLength(0)
  })

  it('done carries no graph state — a lone done frame stays a no-op', () => {
    expect(routeGraphFrame({ type: 'done' })).toBeNull()
    expect(nodes()).toHaveLength(0)
  })
})

// --- socket routing ---------------------------------------------------------
// A fake WebSocket we drive by hand: the hook never opens a real socket (§ test).
class MockSocket {
  static instances: MockSocket[] = []
  url: string
  onopen: (() => void) | null = null
  onmessage: ((message: { data: string }) => void) | null = null
  onclose: ((event: { code: number }) => void) | null = null
  onerror: (() => void) | null = null
  constructor(url: string) {
    this.url = url
    MockSocket.instances.push(this)
  }
  close() {}
  send() {}
}

const scheduled: Array<() => void> = []

const openStream = () =>
  connectGraphStream('job-1', { onFrame: (frame) => routeGraphFrame(frame as GraphFrame), onStatus: () => {} })

const send = (socket: MockSocket, frame: unknown) => socket.onmessage?.({ data: JSON.stringify(frame) })

beforeEach(() => {
  MockSocket.instances = []
  scheduled.length = 0
  vi.stubGlobal('WebSocket', MockSocket)
  // connectRun's reconnect path (reused by the graph stream) defers via window.setTimeout.
  vi.stubGlobal('window', {
    setTimeout: (fn: () => void) => scheduled.push(fn),
    clearTimeout: () => {},
  })
})

afterEach(() => vi.unstubAllGlobals())

describe('connectGraphStream', () => {
  it('routes a snapshot frame off the socket into the store (reset)', () => {
    useGraphStore.getState().mergeDelta({ nodes: [node('old')], edges: [] })
    openStream()
    const socket = MockSocket.instances[0]
    socket.onopen?.()
    send(socket, { type: 'snapshot', nodes: [node('new')], edges: [], labels: ['Molecule'] })
    expect(nodes()).toEqual(['new'])
  })

  it('a reconnect replays the snapshot — merged deltas do not survive the reset', () => {
    openStream()
    const first = MockSocket.instances[0]
    first.onopen?.()
    send(first, { type: 'snapshot', nodes: [node('n1'), node('n2')], edges: [], labels: ['Molecule'] })
    send(first, { type: 'delta', nodes: [node('n3')], edges: [] })
    expect(nodes()).toEqual(['n1', 'n2', 'n3'])

    // Server drops (not the terminal 4004) → backoff, then a fresh socket.
    first.onclose?.({ code: 1006 })
    scheduled.shift()?.()
    const second = MockSocket.instances[1]
    second.onopen?.()
    // The server re-sends the FULL graph on reconnect — 'n3' was never committed.
    send(second, { type: 'snapshot', nodes: [node('n1'), node('n2')], edges: [], labels: ['Molecule'] })

    expect(MockSocket.instances).toHaveLength(2)
    expect(nodes()).toEqual(['n1', 'n2'])
  })

  it('done as the FIRST frame (unknown job, no snapshot) neither throws nor fabricates state', () => {
    openStream()
    const socket = MockSocket.instances[0]
    socket.onopen?.()
    expect(() => send(socket, { type: 'done' })).not.toThrow()
    expect(nodes()).toHaveLength(0)
  })
})
