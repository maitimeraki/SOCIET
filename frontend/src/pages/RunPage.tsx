import { useEffect, useRef, useState } from 'react'
import { NavLink, Navigate, useParams } from 'react-router-dom'
import { connectRun } from '../api/ws'
import type { RunSocket } from '../api/ws'
import type { RunEvent } from '../run/events'
import EventLog from '../components/run/EventLog'

const TABS = ['roster', 'floor', 'verdict', 'agents', 'artifacts'] as const
export type RunTab = (typeof TABS)[number]
export const isRunTab = (value: string | undefined): value is RunTab =>
  (TABS as readonly string[]).includes(value ?? '')

export default function RunPage() {
  const { runId, tab } = useParams()
  const [events, setEvents] = useState<RunEvent[]>([])
  const [connection, setConnection] = useState<'connecting' | 'open' | 'reconnecting' | 'closed'>('connecting')
  const socketRef = useRef<RunSocket | null>(null)

  useEffect(() => {
    if (!runId) return
    socketRef.current = connectRun(runId, {
      onOpen: () => setEvents([]), // full refold from the replay buffer — same rule as the real store (§11.5)
      onEvent: (event) => setEvents((prev) => [...prev, event]),
      onStatus: setConnection,
    })
    return () => socketRef.current?.close()
  }, [runId])

  if (!runId) return null
  if (!isRunTab(tab)) return <Navigate to={`/runs/${runId}/roster`} replace />

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="tnum font-mono text-mono text-paper-mute">run {runId}</p>
        <p className="text-micro text-paper-mute">
          {connection === 'open' ? 'live' : connection === 'reconnecting' ? 'Connection lost — reattaching…' : connection}
        </p>
      </div>
      <nav className="flex items-center gap-1 border-b border-ink-700">
        {TABS.map((name) => (
          <NavLink
            key={name}
            to={`/runs/${runId}/${name}`}
            className={({ isActive }) =>
              `px-3 py-2 text-body capitalize transition-colors ${
                isActive ? 'text-paper shadow-[inset_0_-2px_0_0_var(--color-accent)]' : 'text-paper-dim hover:text-paper'
              }`
            }
          >
            {name}
          </NavLink>
        ))}
      </nav>
      {tab === 'roster' && <p className="text-body text-paper-mute">Waiting for the floor…</p>}
      <EventLog events={events} />
    </div>
  )
}
