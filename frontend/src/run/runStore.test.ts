import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/rest'
import type { RunDoc } from '../api/types'
import { useGraphStore } from '../graph/graphStore'
import { RUN_SAMPLE } from './__fixtures__/run-sample'
import type { AgentProfile, RunEvent } from './events'
import { fold, initialState } from './reducer'
import { useRunStore } from './runStore'

const { connectRun, getRun, getRunGraph } = vi.hoisted(() => ({
  connectRun: vi.fn(),
  getRun: vi.fn(),
  getRunGraph: vi.fn(),
}))

vi.mock('../api/ws', () => ({ connectRun }))
// The corpus read is stubbed, but `ApiError` stays the real class — the typed 404 is the case a
// reopened run's material read is judged by.
vi.mock('../api/rest', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/rest')>()),
  getRun,
  getRunGraph,
}))

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
  getRunGraph.mockReset()
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

describe('runStore reopened-run map (replay = live)', () => {
  const NOW = 1_700_000_000_000
  let frame: FrameRequestCallback | null = null

  beforeEach(() => {
    frame = null
    vi.spyOn(Date, 'now').mockReturnValue(NOW)
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      frame = cb
      return 1
    })
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

  const DATASET = 'ds-1'

  /** One expert the debate stream seats, keyed under the dataset the backend keys the person with. */
  const seat = (name: string): RunEvent => {
    const profile: AgentProfile = {
      agent_id: name,
      identity: { name, archetype: 'analyst', communication_style: 'measured' },
      bio: '',
      detailed_perspective: '',
      stance: 'NEUTRAL',
      intensity: 0.5,
      confidence: 0.5,
      conviction: 0.5,
      cior: 0,
      domain_tags: [],
      communication_radius: 1,
      summary_provenance: [],
      confidence_breakdown: { source_breadth: 0, node_density: 0, relationship_connectivity: 0 },
      graph_snapshot: { dataset_id: DATASET, chunk_count: 2, version_hash: 'v1' },
    }
    return { type: 'agent', index: 1, total: 2, profile }
  }

  /** The run's own events, in the order the stream delivered them — what a reopened doc replays. */
  const EVENTS: RunEvent[] = [
    seat('D. Weber'),
    seat('M. Chen'),
    {
      type: 'round',
      round: 1,
      pairs: [],
      turns: [
        { agent_id: 'D. Weber', agent_name: 'D. Weber', content: 'expand', stance: 'POSITIVE', confidence: 0.8, references: [] },
        { agent_id: 'M. Chen', agent_name: 'M. Chen', content: 'hold', stance: 'NEGATIVE', confidence: 0.7, references: [] },
      ],
    },
    {
      type: 'commit',
      round: 1,
      opinions: 1,
      edges: 1,
      written_nodes: [{ key: `${DATASET}:qh:1:D. Weber`, label: 'Opinion', name: 'D. Weber · pass 1' }],
      written_links: [{ from: `${DATASET}:D. Weber`, to: `${DATASET}:qh:1:D. Weber`, kind: 'STATED' }],
    },
  ]

  /** The corpus read (Task 1.3) — the entries extraction wrote, plus the vocabulary that names them. */
  const CORPUS = {
    dataset_id: DATASET,
    nodes: [
      { id: 'EU', label: 'EU', type: 'Region' },
      { id: 'EuroSteel', label: 'EuroSteel', type: 'Company' },
    ],
    edges: [{ source: 'EuroSteel', target: 'EU', label: 'OPERATES_IN' }],
    labels: ['Company', 'Region'],
    chunk_count: 2,
  }

  const storeContents = () => {
    const { nodes, edges, labels } = useGraphStore.getState()
    return { nodes, edges, labels }
  }

  it('a reopened run rebuilds the map the live stream built, store content for store content', async () => {
    // Producer one — live: the corpus arrived over the build stream, then the events streamed in.
    useGraphStore.getState().applySnapshot(CORPUS)
    for (const event of EVENTS) useRunStore.getState().dispatch(event)
    flushFrame()
    const live = storeContents()

    // Producer two — reopened: the corpus is read over REST and the run doc's events are replayed.
    useGraphStore.setState({ nodes: {}, edges: {}, labels: [], version: 0 })
    getRun.mockResolvedValue(doc({ dataset_id: DATASET, status: 'complete', events: EVENTS }))
    getRunGraph.mockResolvedValue(CORPUS)
    await useRunStore.getState().loadAndConnect('run-1')
    const reopened = storeContents()

    // Not vacuous: the live map really holds both corpus entries, both experts, the opinion, and the
    // two connections — and the two producers never share code (one folds the stream, one composes).
    expect([Object.keys(live.nodes).sort(), Object.keys(live.edges).sort()]).toEqual([
      ['EU', 'EuroSteel', `${DATASET}:D. Weber`, `${DATASET}:M. Chen`, `${DATASET}:qh:1:D. Weber`],
      ['EuroSteel|EU|OPERATES_IN', `${DATASET}:D. Weber|${DATASET}:qh:1:D. Weber|STATED`],
    ])
    // The colour's own state rides the fold on both producers: the opinion carries the position the
    // pass recorded for its holder, so the two maps cannot colour an entry differently (§9.2, F30).
    expect(live.nodes[`${DATASET}:qh:1:D. Weber`].stance).toBe('POSITIVE')
    expect(reopened).toEqual(live)
  })

  it('a run whose material is gone reports it and keeps no previous run’s map', async () => {
    useGraphStore.getState().applySnapshot(CORPUS) // a previously opened run's map is already held
    getRun.mockResolvedValue(doc({ dataset_id: DATASET, status: 'complete', events: EVENTS }))
    getRunGraph.mockRejectedValue(new ApiError(404, 'This run’s corpus is gone.'))

    await useRunStore.getState().loadAndConnect('run-1')

    expect(useRunStore.getState().corpusMissing).toBe(true)
    // The seed REPLACED the store: the material that is gone is not left standing on the map.
    expect(storeContents()).toEqual(expect.objectContaining({ labels: [] }))
    expect(Object.keys(useGraphStore.getState().nodes)).not.toContain('EU')
  })
})
