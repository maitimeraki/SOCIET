import { API_BASE, fetchWsTicket } from './rest'
import type { RunEvent } from '../run/events'

export type StreamStatus = 'connecting' | 'open' | 'reconnecting' | 'closed'

export interface StreamSocket {
  close: () => void
}

/** The single reconnect/backoff scheme — every stream in this file rides it. */
const BACKOFF_MS = [1000, 2000, 4000, 8000, 15000]

/**
 * Auth on the socket: same-origin WebSockets carry the session cookie automatically. When
 * `VITE_WS_AUTH === 'ticket'` the cookie cannot ride the handshake, so each (re)connect first mints
 * a single-use ticket (R4) and appends it — a one-time value, never a long-lived token in the URL.
 * The ticket path is async, so a URL source may return a string (cookie mode, stays synchronous) or a
 * Promise (ticket mode).
 */
type UrlSource = () => string | Promise<string>

const ticketMode = () => import.meta.env.VITE_WS_AUTH === 'ticket'

const urlSource = (path: string): UrlSource => () => {
  const base = `${API_BASE.replace(/^http/, 'ws')}${path}`
  if (!ticketMode()) return base
  return fetchWsTicket().then(({ ticket }) => `${base}?ticket=${encodeURIComponent(ticket)}`)
}

interface StreamOptions {
  /** Called on every (re)connect BEFORE buffered frames arrive — reset the fold here (§11.5). */
  onOpen: () => void
  onMessage: (raw: unknown) => void
  onStatus: (status: StreamStatus) => void
}

function connectStream(getUrl: UrlSource, options: StreamOptions): StreamSocket {
  let socket: WebSocket | null = null
  let closed = false
  let attempt = 0
  let timer: number | undefined

  const retry = () => {
    if (closed) return
    options.onStatus('reconnecting')
    const delay = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)]
    attempt += 1
    timer = window.setTimeout(open, delay)
  }

  const startSocket = (url: string) => {
    if (closed) return
    socket = new WebSocket(url)
    socket.onopen = () => {
      attempt = 0
      options.onOpen()
      options.onStatus('open')
    }
    socket.onmessage = (message: MessageEvent<string>) => {
      let parsed: unknown
      try {
        parsed = JSON.parse(message.data)
      } catch {
        return
      }
      options.onMessage(parsed)
    }
    socket.onclose = (event) => {
      if (closed) return
      if (event.code === 4004) {
        // Terminal: the job was rejected or is gone — a reconnect cannot succeed.
        closed = true
        if (timer !== undefined) window.clearTimeout(timer)
        options.onStatus('closed')
        return
      }
      retry()
    }
    socket.onerror = () => socket?.close()
  }

  const open = () => {
    if (closed) return
    options.onStatus(attempt === 0 ? 'connecting' : 'reconnecting')
    const resolved = getUrl()
    // Cookie mode resolves synchronously so the socket exists the moment connect*() returns.
    if (typeof resolved === 'string') startSocket(resolved)
    else resolved.then(startSocket, retry) // ticket mint failed — a transient drop, not terminal
  }

  open()
  return {
    close: () => {
      closed = true
      if (timer !== undefined) window.clearTimeout(timer)
      socket?.close()
    },
  }
}

export type RunSocket = StreamSocket

export interface RunSocketOptions {
  /** Called on every (re)connect BEFORE buffered events arrive — reset the fold here (§11.5). */
  onOpen: () => void
  onEvent: (event: RunEvent) => void
  onStatus: (status: StreamStatus) => void
}

export function connectRun(jobId: string, options: RunSocketOptions): RunSocket {
  return connectStream(urlSource(`/api/v1/simulate/${jobId}/stream`), {
    onOpen: options.onOpen,
    onStatus: options.onStatus,
    onMessage: (raw) => {
      const event = raw as RunEvent
      if (event.type === 'ping' || event.type === 'ack') return // transport keep-alives, never folded
      options.onEvent(event)
    },
  })
}

export interface GraphStreamOptions {
  /** Every frame off the socket, verbatim: `snapshot` | `delta` | `vocabulary` | `error` | `done`. */
  onFrame: (frame: unknown) => void
  onStatus: (status: StreamStatus) => void
}

/**
 * `/api/v1/simulate/{id}/graph_stream` — the graph build's live feed. Reconnect is transport-only:
 * the server re-sends a full `snapshot` on every (re)connect, so resetting is the caller's
 * job via the frame, not an `onOpen` hook.
 */
export function connectGraphStream(jobId: string, options: GraphStreamOptions): StreamSocket {
  return connectStream(urlSource(`/api/v1/simulate/${jobId}/graph_stream`), {
    onOpen: () => {},
    onStatus: options.onStatus,
    onMessage: options.onFrame,
  })
}
