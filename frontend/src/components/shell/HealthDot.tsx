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

  const dot =
    state === 'online' ? 'bg-stance-pos' : state === 'offline' ? 'bg-route' : 'bg-ink-4'
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
      <span className="tnum font-measurement text-mono text-ink-3">{label}</span>
    </span>
  )
}
