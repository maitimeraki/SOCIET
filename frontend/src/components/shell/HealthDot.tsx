import { useCallback, useEffect, useState } from 'react'
import { health } from '../../api/rest'

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
  // §7.3/§12.3 — the customer sees Connected or Working, never server or API jargon.
  const label =
    state === 'online' ? 'Connected' : state === 'offline' ? 'Working' : 'Checking…'

  return (
    <span className="inline-flex items-center gap-2">
      <span aria-hidden="true" className={`h-2 w-2 rounded-full ${dot}`} />
      {/* The dot itself is aria-hidden, so this word is the only carrier of the status; ink-2
          measures 9.1:1 on the bone rail. */}
      <span className="tnum font-mono text-mono text-ink-2">{label}</span>
    </span>
  )
}
