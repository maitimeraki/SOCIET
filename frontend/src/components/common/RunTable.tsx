import { Link } from 'react-router-dom'
import { CheckCircle, Warning, XCircle } from '@phosphor-icons/react'
import type { RunSummary } from '../../api/types'
import { fmtDate } from '../../utils/format'
import Skeleton from '../ui/Skeleton'
import { asStance } from '../../run/events'
import StanceChip from './StanceChip'

function OutcomeCell({ run }: { run: RunSummary }) {
  if (run.status === 'failed')
    return (
      <span className="inline-flex items-center gap-1.5 text-critical">
        <XCircle size={14} aria-hidden="true" /> failed
      </span>
    )
  if (run.status === 'interrupted')
    return (
      <span className="inline-flex items-center gap-1.5 text-brass">
        <Warning size={14} aria-hidden="true" /> interrupted
      </span>
    )
  if (run.status === 'running' || run.status === 'queued')
    return <span className="text-paper-mute">{run.status === 'running' ? 'deliberating…' : 'queued'}</span>
  return (
    <span className="inline-flex items-center gap-2">
      {run.verdict_stance && <StanceChip stance={asStance(run.verdict_stance)} size="sm" />}
      {run.converged ? (
        <span className="inline-flex items-center gap-1 text-good">
          <CheckCircle size={14} aria-hidden="true" /> converged
        </span>
      ) : (
        <span className="text-paper-mute">plurality</span>
      )}
    </span>
  )
}

export default function RunTable({ runs, loading = false }: { runs: RunSummary[]; loading?: boolean }) {
  if (loading) {
    return (
      <div className="space-y-3 py-2">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    )
  }
  if (runs.length === 0) return null // callers own the empty state (§13)
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-body">
        <thead>
          <tr className="text-label uppercase text-paper-mute">
            <th className="py-2 pr-4 text-left font-medium">Question</th>
            <th className="py-2 pr-4 text-left font-medium">Corpus</th>
            <th className="tnum py-2 pr-4 text-right font-medium">Rounds</th>
            <th className="py-2 pr-4 text-left font-medium">Outcome</th>
            <th className="py-2 text-right font-medium">Created</th>
          </tr>
        </thead>
        <tbody className="text-paper-dim">
          {runs.map((run) => (
            <tr key={run.run_id} className="border-t border-ink-700 transition-colors hover:bg-ink-800">
              <td className="max-w-[360px] py-2.5 pr-4">
                <Link to={`/runs/${run.run_id}`} className="block truncate text-paper hover:text-accent">
                  {run.query}
                </Link>
              </td>
              <td className="tnum py-2.5 pr-4 font-mono text-mono text-paper-mute">{run.dataset_id}</td>
              <td className="tnum py-2.5 pr-4 text-right">{run.rounds_executed}</td>
              <td className="py-2.5 pr-4">
                <OutcomeCell run={run} />
              </td>
              <td className="tnum py-2.5 text-right font-mono text-mono text-paper-mute">{fmtDate(run.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
