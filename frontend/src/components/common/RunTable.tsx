import { Link } from 'react-router-dom'
import type { RunSummary } from '../../api/types'
import { fmtDate, truncateId } from '../../utils/format'
import Skeleton from '../ui/Skeleton'
import Table from '../ui/Table'
import StanceChip from './StanceChip'
import StateChip from './StateChip'

/**
 * §8.4 Decisions — the process of each decision: when it ran, the question, the corpus it drew from,
 * the passes completed, the outcome and the status.
 *
 * Field mapping against the live `GET /api/v1/simulate/debates` item (`run_doc._summarize`):
 *   · when     → `created_at`
 *   · question → `query`
 *   · corpus   → `corpus_label`, falling back to the corpus id `dataset_id` when the run named none
 *   · passes   → `rounds_executed`
 *   · outcome  → `verdict_stance` (StanceChip: symbol + colour + word); absent → an honest "still running"
 *   · status   → `status` (StateChip)
 * Every rendered field comes from the payload — nothing is derived to fill a column.
 */
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

  const corpus = (run: RunSummary) => run.corpus_label ?? truncateId(run.dataset_id, 8, 4)
  const outcome = (run: RunSummary) =>
    run.verdict_stance ? (
      <StanceChip stance={run.verdict_stance} />
    ) : (
      // No verdict yet is a fact, not a blank cell (§D7 honesty).
      <span className="text-ink-3">still running</span>
    )

  return (
    <>
      <div className="hidden overflow-x-auto md:block">
        <Table
          head={
            <tr>
              <th className="py-2 pr-4 text-left font-medium">When</th>
              <th className="py-2 pr-4 text-left font-medium">Question</th>
              <th className="py-2 pr-4 text-left font-medium">Corpus</th>
              <th className="tnum py-2 pr-4 text-right font-medium">Passes</th>
              <th className="py-2 pr-4 text-left font-medium">Outcome</th>
              <th className="py-2 text-left font-medium">Status</th>
            </tr>
          }
        >
          {runs.map((run) => (
            <tr key={run.run_id} className="transition-colors hover:bg-ground-2">
              <td className="tnum py-2.5 pr-4 font-measurement text-mono text-ink-3">{fmtDate(run.created_at)}</td>
              <td className="max-w-[360px] py-2.5 pr-4">
                <Link to={`/runs/${run.run_id}`} className="block truncate text-ink hover:text-accent">
                  {run.query}
                </Link>
              </td>
              <td className="py-2.5 pr-4 font-measurement text-mono text-ink-3">{corpus(run)}</td>
              <td className="tnum py-2.5 pr-4 text-right font-measurement text-mono text-ink-2">
                {run.rounds_executed}
              </td>
              <td className="py-2.5 pr-4">{outcome(run)}</td>
              <td className="py-2.5">
                <StateChip state={run.status} />
              </td>
            </tr>
          ))}
        </Table>
      </div>

      {/* Under md the timeline collapses to stacked cards (§6 responsive). */}
      <ul className="space-y-2 md:hidden">
        {runs.map((run) => (
          <li key={run.run_id} className="border-t border-ink-4 pt-3">
            <div className="flex items-start justify-between gap-3">
              <Link to={`/runs/${run.run_id}`} className="text-body text-ink hover:text-accent">
                {run.query}
              </Link>
              <StateChip state={run.status} />
            </div>
            <dl className="mt-2 grid grid-cols-2 gap-2 text-micro">
              <div>
                <dt className="text-ink-3">When</dt>
                <dd className="tnum font-measurement text-mono text-ink-2">{fmtDate(run.created_at)}</dd>
              </div>
              <div>
                <dt className="text-ink-3">Corpus</dt>
                <dd className="font-measurement text-mono text-ink-2">{corpus(run)}</dd>
              </div>
              <div>
                <dt className="text-ink-3">Passes</dt>
                <dd className="tnum font-measurement text-mono text-ink-2">{run.rounds_executed}</dd>
              </div>
              <div>
                <dt className="text-ink-3">Outcome</dt>
                <dd>{outcome(run)}</dd>
              </div>
            </dl>
          </li>
        ))}
      </ul>
    </>
  )
}
