import { useCallback, useEffect, useState } from 'react'
import { API_BASE, health } from '../../api/rest'

type HealthState = 'checking' | 'online' | 'offline'

export default function HealthDot() {
  const [state, setState] = useState<HealthState>('checking')

  const check = useCallback(() => {
    health()
      .then(() => setState('online'))
      .catch(() => setState('offline'))
  }, [])

  useEffect(() => {
    check()
    const timer = window.setInterval(check, 30_000)
    return () => window.clearInterval(timer)
  }, [check])

  // The mark is the map's own reading, never a stance hue: a live reading takes --accent, a failed one
  // the danger hue, and an unread one the idle hairline ink.
  const dot = state === 'online' ? 'bg-accent' : state === 'offline' ? 'bg-danger' : 'bg-hairline'
  const label =
    state === 'online'
      ? 'API online'
      : state === 'offline'
        ? import.meta.env.DEV
          ? 'API unreachable — start uvicorn'
          : 'connecting…'
        : 'checking…'

  return (
    <span className="inline-flex items-center gap-2" title={`Checked ${API_BASE}/health`}>
      <span aria-hidden="true" className={`h-2 w-2 rounded-full ${dot}`} />
      {/* ink-2, not ink-3: the dot sits on the rail's --ground-2 (#F1F5F9), where ink-3 measures
          4.34:1 — under §12's floor. The dot itself is aria-hidden, so this word is the only
          carrier of the status; ink-2 measures 9.45:1 there. */}
      <span className="tnum font-mono text-mono text-ink-2">{label}</span>
    </span>
  )
}
