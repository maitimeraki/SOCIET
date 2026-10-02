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
    state === 'online' ? 'bg-good' : state === 'offline' ? 'bg-critical' : 'bg-paper-faint'
  const label = state === 'online' ? 'API online' : state === 'offline' ? 'API unreachable — start uvicorn' : 'checking…'

  return (
    <span className="inline-flex items-center gap-2" title={`Checked ${API_BASE}/health`}>
      <span aria-hidden="true" className={`h-2 w-2 rounded-full ${dot}`} />
      <span className="tnum font-mono text-mono text-paper-mute">{label}</span>
    </span>
  )
}
