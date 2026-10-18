import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RunDoc } from '../api/types'
import { useGraphStore } from '../graph/graphStore'
import { RUN_SAMPLE } from './__fixtures__/run-sample'
import type { RunEvent } from './events'
import { fold, initialState } from './reducer'
import { useRunStore } from './runStore'

const { connectRun, getRun } = vi.hoisted(() => ({ connectRun: vi.fn(), getRun: vi.fn() }))

vi.mock('../api/ws', () => ({ connectRun }))
vi.mock('../api/rest', () => ({ getRun }))

const doc = (patch: Partial<RunDoc> = {}): RunDoc => ({
  run_id: 'run-1',
  created_at: '2026-10-03T00:00:00Z',
  query: 'Should we expand?',
  dataset_id: 'ds-1',
  config: {} as RunDoc['config'],
  status: 'running',
  events: [],
  ...patch,
})

beforeEach(() => {
  connectRun.mockReset()
  connectRun.mockReturnValue({ close: vi.fn() })
  getRun.mockReset()
  useRunStore.setState({ run: initialState, events: [], connection: 'idle', socket: null })
})

describe('runStore.loadAndConnect supersession', () => {
  it('two concurrent loads connect exactly once (StrictMode double-invoke)', async () => {
    getRun.mockResolvedValue(doc())
    await Promise.all([useRunStore.getState().loadAndConnect('run-1'), useRunStore.getState().loadAndConnect('run-1')])
    expect(connectRun).toHaveBeenCalledTimes(1)
    expect(connectRun).toHaveBeenCalledWith('run-1', expect.any(Object))
  })

  it('disconnect() during an in-flight load cancels it', async () => {
    let release!: (value: RunDoc) => void
    getRun.mockImplementation(() => new Promise<RunDoc>((resolve) => (release = resolve)))
    const pending = useRunStore.getState().loadAndConnect('run-1')
    useRunStore.getState().disconnect()
    release(doc())
    await pending
    expect(connectRun).not.toHaveBeenCalled()
  })
})

describe('runStore rAF batching', () => {
  const NOW = 1_700_000_000_000
  // A controllable frame: the stub captures the pending callback so a test decides when the frame
  // lands. No jsdom in this repo, so rAF would otherwise be missing entirely (runStore falls back
  // to setTimeout) and the flush could never be driven deterministically.
  let frame: FrameRequestCallback | null = null

  beforeEach(() => {
    frame = null
    vi.spyOn(Date, 'now').mockReturnValue(NOW)
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      frame = cb
      return 1
    })
    // The graph store is a module singleton — reset it so the map assertions are absolute.
    useGraphStore.setState({ nodes: {}, edges: {}, labels: [], version: 0 })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  const flushFrame = () => {
    const cb = frame
    frame = null
    cb?.(0)
  }

  it('folds a whole burst in arrival order, matching the per-event fold', () => {
    for (const event of RUN_SAMPLE) useRunStore.getState().dispatch(event)

    // Nothing folded yet — the burst is buffered until the frame lands.
    expect(useRunStore.getState().events).toHaveLength(0)

    flushFrame()

    expect(useRunStore.getState().events).toEqual(RUN_SAMPLE)
    // The fold still runs through applyEvent, so batched live === per-event replay (§11.2).
    expect(useRunStore.getState().run).toEqual(fold(RUN_SAMPLE, () => NOW))
  })

  it('folds once per frame, not once per event', () => {
    let notifications = 0
    const unsubscribe = useRunStore.subscribe(() => notifications++)

    for (const event of RUN_SAMPLE.slice(0, 6)) useRunStore.getState().dispatch(event)
    expect(notifications).toBe(0)
    flushFrame()
    expect(notifications).toBe(1)
    expect(useRunStore.getState().events).toHaveLength(6)

    // A later burst is a second fold — still one per frame, not one per event.
    for (const event of RUN_SAMPLE.slice(6, 10)) useRunStore.getState().dispatch(event)
    flushFrame()
    expect(notifications).toBe(2)
    expect(useRunStore.getState().events).toHaveLength(10)

    unsubscribe()
  })

  it('keeps arrival order across frames', () => {
    useRunStore.getState().dispatch(RUN_SAMPLE[0])
    useRunStore.getState().dispatch(RUN_SAMPLE[1])
    flushFrame()
    useRunStore.getState().dispatch(RUN_SAMPLE[2])
    flushFrame()

    expect(useRunStore.getState().events).toEqual(RUN_SAMPLE.slice(0, 3))
  })

  it('grows the one map from a dispatched agent and commit as the frame lands (the live path)', () => {
    const seated = RUN_SAMPLE.find((event) => event.type === 'agent') as Extract<RunEvent, { type: 'agent' }>
    const agent: RunEvent = {
      ...seated,
      profile: { ...seated.profile, graph_snapshot: { dataset_id: 'ds-1', chunk_count: 3, version_hash: 'v1' } },
    }
    const commit: RunEvent = {
      type: 'commit',
      round: 1,
      opinions: 1,
      edges: 1,
      written_nodes: [{ key: 'ds-1:qh:1:D. Weber', label: 'Opinion', name: 'D. Weber · pass 1' }],
      written_links: [{ from: 'ds-1:D. Weber', to: 'ds-1:qh:1:D. Weber', kind: 'STATED' }],
    }

    useRunStore.getState().dispatch(agent)
    useRunStore.getState().dispatch(commit)
    flushFrame()

    const { nodes, edges } = useGraphStore.getState()
    expect([Object.keys(nodes), Object.keys(edges)]).toEqual([
      ['ds-1:D. Weber', 'ds-1:qh:1:D. Weber'],
      ['ds-1:D. Weber|ds-1:qh:1:D. Weber|STATED'],
    ])
  })
})
