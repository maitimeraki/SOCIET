import { create } from 'zustand'
import { getRun } from '../api/rest'
import { connectRun } from '../api/ws'
import type { RunSocket } from '../api/ws'
import { useGraphStore } from '../graph/graphStore'
import type { RunEvent } from './events'
import { applyEvent, initialState } from './reducer'
import type { RunState } from './reducer'

interface RunStoreState {
  run: RunState
  /** Raw arrival-ordered log — the Artifacts raw view and the export JSON (§7.9, §7.7). */
  events: RunEvent[]
  connection: 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed'
  socket: RunSocket | null
  loadAndConnect: (runId: string) => Promise<void>
  dispatch: (event: RunEvent) => void
  reset: () => void
  disconnect: () => void
}

/** Supersession counter: every loadAndConnect/disconnect invalidates earlier in-flight loads. */
let loadGeneration = 0

/**
 * Events received since the last animation frame. A stream delivers a burst of deltas between two
 * frames; folding each as it arrives re-renders every subscriber and copies the whole event log per
 * event — O(n²) over a run. Buffering them and folding the batch in one `set` costs one render and
 * one log copy per frame, in arrival order.
 *
 * ponytail: one frame still re-runs `applyEvent` per buffered event and copies the log, so a frame
 * carrying a huge batch is O(n) blocking work — fine at streaming rates. Past ~10k events per frame,
 * move the run state behind a module ref + version counter and let subscribers pull, instead of a
 * zustand `set` per frame.
 */
let pending: RunEvent[] = []
let scheduled = false

// rAF is absent outside a DOM (this repo's suite runs in Node), so fall back to a macrotask.
const scheduleFrame = (flush: () => void): void => {
  if (typeof requestAnimationFrame === 'function') requestAnimationFrame(flush)
  else setTimeout(flush, 0)
}

/**
 * Grow the one map (D14) from the debate stream. Each `agent` event seats one expert entry, keyed as
 * the backend keys the stored person; each `commit` event adds the entries and connections it reports
 * it wrote, verbatim (D7). Everything else in the stream leaves the map alone. Idempotent, so a
 * reconnect's replay of the buffer adds nothing new.
 */
const foldIntoMap = (event: RunEvent): void => {
  const { mergeExpert, mergeOpinions } = useGraphStore.getState()
  if (event.type === 'agent') {
    const datasetId = event.profile.graph_snapshot?.dataset_id
    // Without a dataset there is no Persona key to mirror: leave the entry unseated rather than key
    // it off a fabricated id. The live payload always carries one.
    if (datasetId) mergeExpert({ datasetId, name: event.profile.identity.name })
    return
  }
  if (event.type === 'commit') mergeOpinions(event.written_nodes ?? [], event.written_links ?? [])
}

export const useRunStore = create<RunStoreState>((set, get) => {
  // Fold every buffered event in ONE set. The fold still runs through `applyEvent`, so a batched
  // live stream and a per-event replay produce the same state (§11.2) — only the timing changes.
  const flush = () => {
    scheduled = false
    if (pending.length === 0) return
    const batch = pending
    pending = []
    set((state) => {
      let run = state.run
      for (const event of batch) run = applyEvent(run, event, Date.now())
      return { run, events: [...state.events, ...batch] }
    })
    // Same frame, same batch: the map grows alongside the run state, once per frame — not once per
    // event, which is the per-event render cost this batching exists to avoid.
    for (const event of batch) foldIntoMap(event)
  }

  return {
    run: initialState,
    events: [],
    connection: 'idle',
    socket: null,

    // Config rides the run doc only — the replayed event buffer carries none, so a
    // reset on (re)connect must keep it or the header/tape lose the run's settings.
    reset: () => {
      pending = [] // pre-open arrivals belong to the old connection; the refold replaces them
      set((state) => ({ run: { ...initialState, runId: state.run.runId, config: state.run.config }, events: [] }))
    },

    dispatch: (event) => {
      pending.push(event)
      if (scheduled) return
      scheduled = true
      scheduleFrame(flush)
    },

    disconnect: () => {
      loadGeneration++
      pending = [] // a run switch discards the previous run's unfolded events; its doc refolds them
      get().socket?.close()
      set({ socket: null, connection: 'idle' })
    },

    loadAndConnect: async (runId: string) => {
      get().disconnect()
      const generation = ++loadGeneration
      set({ run: { ...initialState, runId }, events: [], connection: 'connecting' })

      // Instant paint for reopened / mid-run views. The WS replay below refolds the
      // full buffer, so this fold is display-only and the seam is invisible (§11.5).
      try {
        const doc = await getRun(runId)
        if (generation !== loadGeneration) return
        set({
          run: doc.events.reduce<RunState>(
            (state, event) => applyEvent(state, event, Date.now()),
            { ...initialState, runId, config: doc.config ?? null },
          ),
          events: doc.events,
        })
        if (doc.status === 'complete' || doc.status === 'failed') {
          set({ connection: 'closed' })
          return
        }
      } catch {
        // Run-doc endpoint is Task 20; a live run needs no doc to fold.
      }

      if (generation !== loadGeneration) return
      const socket = connectRun(runId, {
        // Sequence truth is the server's buffer: reset, then refold the replay (§11.5).
        onOpen: () => get().reset(),
        onEvent: (event) => get().dispatch(event),
        onStatus: (connection) => set({ connection }),
      })
      set({ socket })
    },
  }
})
