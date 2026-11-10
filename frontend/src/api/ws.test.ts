import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { connectGraphStream, connectRun } from './ws'

// A fake WebSocket we never open: the constructor records the URL it was handed.
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
}

beforeEach(() => {
  MockSocket.instances = []
  vi.stubGlobal('WebSocket', MockSocket)
  // The reconnect path defers via window.setTimeout; never fires here.
  vi.stubGlobal('window', { setTimeout: () => 0, clearTimeout: () => {} })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

const runOptions = { onOpen: () => {}, onEvent: () => {}, onStatus: () => {} }
const graphOptions = { onFrame: () => {}, onStatus: () => {} }

describe('connectRun', () => {
  it('opens the v1 stream path — cookie auth rides the same-origin handshake', () => {
    connectRun('job-1', runOptions)
    expect(MockSocket.instances[0].url).toBe('/api/v1/simulate/job-1/stream')
  })

  it('mints a one-time ticket and appends it when VITE_WS_AUTH=ticket', async () => {
    vi.stubEnv('VITE_WS_AUTH', 'ticket')
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ticket: 't-9', expires_in: 30 })))
    vi.stubGlobal('fetch', fetchMock)

    connectRun('job-2', runOptions)

    await vi.waitFor(() => expect(MockSocket.instances).toHaveLength(1))
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/ws-ticket')
    expect(fetchMock.mock.calls[0][1].method).toBe('POST')
    expect(MockSocket.instances[0].url).toBe('/api/v1/simulate/job-2/stream?ticket=t-9')
  })
})

describe('connectGraphStream', () => {
  it('opens the v1 graph_stream path — cookie auth rides the same-origin handshake', () => {
    connectGraphStream('job-1', graphOptions)
    expect(MockSocket.instances[0].url).toBe('/api/v1/simulate/job-1/graph_stream')
  })

  it('mints a one-time ticket and appends it when VITE_WS_AUTH=ticket', async () => {
    vi.stubEnv('VITE_WS_AUTH', 'ticket')
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ticket: 'g-7', expires_in: 30 })))
    vi.stubGlobal('fetch', fetchMock)

    connectGraphStream('job-2', graphOptions)

    await vi.waitFor(() => expect(MockSocket.instances).toHaveLength(1))
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/ws-ticket')
    expect(MockSocket.instances[0].url).toBe('/api/v1/simulate/job-2/graph_stream?ticket=g-7')
  })
})
