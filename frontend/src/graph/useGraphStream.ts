import { useEffect, useState } from 'react'
import { connectGraphStream } from '../api/ws'
import type { StreamStatus } from '../api/ws'
import { useGraphStore } from './graphStore'
import type { GraphEdge, GraphNode } from './graphStore'

/** A frame on `/simulate/{id}/graph_stream`, matching the backend wire shapes verbatim. */
export type GraphFrame =
  | { type: 'snapshot'; nodes: GraphNode[]; edges: GraphEdge[]; labels: string[] }
  | { type: 'delta'; nodes: GraphNode[]; edges: GraphEdge[] }
  | { type: 'vocabulary'; labels: string[] }
  | { type: 'error'; chunk_id?: string; message: string }
  | { type: 'done' }

/** A chunk the build retried and skipped. Surfaced by the hook, never merged as graph data. */
export interface GraphStreamError {
  chunk_id?: string
  message: string
}

export interface GraphStreamState {
  status: StreamStatus
  /** The build finished (`done`). May be true with an empty graph — a done frame can arrive alone. */
  done: boolean
  /** Skipped-chunk errors, in arrival order. Kept out of the graph store. */
  errors: GraphStreamError[]
}

/**
 * Route a graph frame into the store. Only `snapshot`/`delta`/`vocabulary` carry graph state;
 * `done` is a signal and `error` is surfaced to the caller — neither touches the graph.
 * @returns the error to surface for an `error` frame, else `null`.
 */
export function routeGraphFrame(frame: GraphFrame): GraphStreamError | null {
  const { applySnapshot, mergeDelta, mergeVocabulary } = useGraphStore.getState()
  switch (frame.type) {
    case 'snapshot':
      applySnapshot(frame) // reset — a reconnect cannot duplicate nodes
      return null
    case 'delta':
      mergeDelta(frame)
      return null
    case 'vocabulary':
      mergeVocabulary(frame.labels)
      return null
    case 'error':
      return { chunk_id: frame.chunk_id, message: frame.message }
    case 'done':
      return null
  }
}

const emptyState = (): GraphStreamState => ({ status: 'connecting', done: false, errors: [] })

/**
 * Own the graph build's socket for `jobId` and fold its frames into the graph store.
 * The store's graph is the only channel; nothing here polls REST.
 */
export function useGraphStream(jobId: string): GraphStreamState {
  const [state, setState] = useState<GraphStreamState>(emptyState)
  const [tracked, setTracked] = useState(jobId)

  // A new jobId is a fresh stream — drop the previous job's status/errors (React's
  // "reset state when a prop changes" pattern, kept out of the effect to avoid a cascading render).
  if (tracked !== jobId) {
    setTracked(jobId)
    setState(emptyState())
  }

  useEffect(() => {
    const socket = connectGraphStream(jobId, {
      onStatus: (status) => setState((prev) => ({ ...prev, status })),
      onFrame: (raw) => {
        const frame = raw as GraphFrame
        const error = routeGraphFrame(frame)
        setState((prev) => ({
          ...prev,
          done: prev.done || frame.type === 'done',
          errors: error ? [...prev.errors, error] : prev.errors,
        }))
      },
    })
    return () => socket.close()
  }, [jobId])

  return state
}
