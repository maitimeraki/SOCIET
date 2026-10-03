import { API_BASE } from './rest'
import type { RunEvent } from '../run/events'

export interface RunSocket {
  close: () => void
}

export interface RunSocketOptions {
  /** Called on every (re)connect BEFORE buffered events arrive — reset the fold here (§11.5). */
  onOpen: () => void
  onEvent: (event: RunEvent) => void
  onStatus: (status: 'connecting' | 'open' | 'reconnecting' | 'closed') => void
}

const BACKOFF_MS = [1000, 2000, 4000, 8000, 15000]

export function connectRun(jobId: string, options: RunSocketOptions): RunSocket {
  const url = `${API_BASE.replace(/^http/, 'ws')}/simulate/${jobId}/stream`
  let socket: WebSocket | null = null
  let closed = false
  let attempt = 0
  let timer: number | undefined

  const open = () => {
    if (closed) return
    options.onStatus(attempt === 0 ? 'connecting' : 'reconnecting')
    socket = new WebSocket(url)
    socket.onopen = () => {
      attempt = 0
      options.onOpen()
      options.onStatus('open')
    }
    socket.onmessage = (message: MessageEvent<string>) => {
      let event: RunEvent
      try {
        event = JSON.parse(message.data) as RunEvent
      } catch {
        return
      }
      if (event.type === 'ping' || event.type === 'ack') return // transport keep-alives, never folded
      options.onEvent(event)
    }
    socket.onclose = () => {
      if (closed) return
      options.onStatus('reconnecting')
      const delay = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)]
      attempt += 1
      timer = window.setTimeout(open, delay)
    }
    socket.onerror = () => socket?.close()
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
