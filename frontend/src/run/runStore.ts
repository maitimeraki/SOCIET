import { create } from 'zustand'
import { getRun } from '../api/rest'
import { connectRun } from '../api/ws'
import type { RunSocket } from '../api/ws'
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

export const useRunStore = create<RunStoreState>((set, get) => ({
  run: initialState,
  events: [],
  connection: 'idle',
  socket: null,

  reset: () => set((state) => ({ run: { ...initialState, runId: state.run.runId }, events: [] })),

  dispatch: (event) =>
    set((state) => ({
      run: applyEvent(state.run, event, Date.now()),
      events: [...state.events, event],
    })),

  disconnect: () => {
    loadGeneration++
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
        run: doc.events.reduce<RunState>((state, event) => applyEvent(state, event, Date.now()), { ...initialState, runId }),
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
}))
