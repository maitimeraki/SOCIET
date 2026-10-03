import { useEffect, useState } from 'react'
import { Copy } from '@phosphor-icons/react'
import type { RunState } from '../../run/reducer'
import { currentRound } from '../../run/selectors'
import { fmtElapsed, truncateId } from '../../utils/format'
import StateChip from '../common/StateChip'
import type { RunStateWord } from '../common/StateChip'
import IconButton from '../ui/IconButton'
import { toast } from '../ui/Toast'

export default function RunHeader({
  run,
  connection,
  maxRounds,
}: {
  run: RunState
  connection: string
  maxRounds: number | null
}) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (run.status !== 'running') return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [run.status])

  const chip: RunStateWord =
    run.status === 'failed'
      ? 'failed'
      : run.verdict?.converged
        ? 'converged'
        : run.status === 'complete'
          ? 'complete'
          : run.status === 'running'
            ? 'running'
            : 'queued'
  const startedAt = run.stages[0]?.at
  const elapsed = run.status === 'running' && startedAt ? fmtElapsed((now - startedAt) / 1000) : null
  const round = currentRound(run)

  return (
    <div className="space-y-2">
      <p className="font-serif text-title text-paper">{run.query || 'Waiting for the floor…'}</p>
      {run.intent?.core_question && (
        <p className="tnum font-mono text-mono text-paper-mute">reading as: {run.intent.core_question}</p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <StateChip state={chip} />
        {round > 0 && (
          <span className="tnum font-mono text-mono text-paper-dim">
            ROUND {round}
            {maxRounds ? `/${maxRounds}` : ''}
          </span>
        )}
        {elapsed && <span className="tnum font-mono text-mono text-paper-dim">{elapsed} elapsed</span>}
        {run.runId && (
          <span className="flex items-center gap-1">
            <span className="tnum font-mono text-mono text-paper-mute">run {truncateId(run.runId)}</span>
            <IconButton
              label="Copy run id"
              onClick={() => {
                void navigator.clipboard.writeText(run.runId ?? '')
                toast('neutral', 'Copied')
              }}
            >
              <Copy size={12} aria-hidden="true" />
            </IconButton>
          </span>
        )}
        {connection === 'reconnecting' && <span className="text-micro text-brass">Connection lost — reattaching…</span>}
      </div>
    </div>
  )
}
