import { Link } from 'react-router-dom'
import type { RunSummary } from '../../api/types'
import { fmtDate, truncateId } from '../../utils/format'
import Skeleton from '../ui/Skeleton'
import StanceChip from './StanceChip'
import StateChip from './StateChip'

/**
 * §8.4 Decisions — a list of the decisions themselves, question first: the question is the heading
 * and the whole card opens the run. Beneath it, one quiet line carries the outcome, the date, the
 * passes completed, the corpus it drew from and the status.
 *
 * Field mapping against the live `GET /api/v1/simulate/debates` item (`run_doc._summarize`):
 *   · when     → `created_at`
 *   · question → `query`
 *   · corpus   → `corpus_label`, falling back to the corpus id `dataset_id`; neither → an honest dash
 *   · passes   → `rounds_executed`
 *   · outcome  → `verdict_stance` (StanceChip: symbol + colour + word); absent → copy that matches status
 *   · status   → `status` (StateChip)
 * Every rendered field comes from the payload — nothing is derived to fill a field.
 */
const DASH = '—'

const passes = (count: number): string => `${count} ${count === 1 ? 'pass' : 'passes'}`

export default function RunTable({ runs, loading = false }: { runs: RunSummary[]; loading?: boolean }) {
  if (loading) {
    return (
      <div className="space-y-3 py-2">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-20 w-full" />
        ))}
      </div>
    )
  }
  if (runs.length === 0) return null // callers own the empty state (§13)

  // `dataset_id` can be null at runtime (`meta.get("dataset_id")`) even though the type says string.
  const corpus = (run: RunSummary) =>
    run.corpus_label ?? (run.dataset_id ? truncateId(run.dataset_id, 8, 4) : DASH)
  const outcome = (run: RunSummary) => {
    if (run.verdict_stance) return <StanceChip stance={run.verdict_stance} />
    // No verdict, and the copy says WHY (§D7 honesty): a run still going has none yet; a run that has
    // ENDED without one (failed, interrupted, complete with no clusters) is not "still running".
    const stillGoing = run.status === 'running' || run.status === 'queued'
    return <span className="text-ink-3">{stillGoing ? 'still running' : 'No outcome yet'}</span>
  }

  return (
    <ul className="space-y-3">
      {runs.map((run) => (
        <li key={run.run_id}>
          <Link
            to={`/runs/${run.run_id}`}
            className="block rounded-md border border-border bg-canvas p-4 transition-colors hover:border-border-strong hover:bg-ground-2"
          >
            <h3 className="text-heading text-ink">{run.query}</h3>
            <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-micro text-ink-3">
              {outcome(run)}
              <span className="tnum font-measurement text-mono">{fmtDate(run.created_at)}</span>
              <span className="tnum font-measurement text-mono">{passes(run.rounds_executed)}</span>
              <span className="font-measurement text-mono">{corpus(run)}</span>
              <StateChip state={run.status} />
            </p>
          </Link>
        </li>
      ))}
    </ul>
  )
}
