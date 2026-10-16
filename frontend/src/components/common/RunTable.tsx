import { Link } from 'react-router-dom'
import type { RunSummary } from '../../api/types'
import { fmtDate, truncateId } from '../../utils/format'
import Skeleton from '../ui/Skeleton'
import StateChip from './StateChip'

/**
 * The run timeline (§3.3): timestamp · question · documents used · status · agent count.
 *
 * Field mapping against the live `GET /api/v1/simulate/debates` item (`run_doc._summarize`):
 *   · timestamp      → `created_at`
 *   · question       → `query`
 *   · documents used → `dataset_id` — the corpus the run drew from; the payload carries NO document
 *                      count, so the corpus id is the honest available proxy, never a fabricated count
 *   · status         → `status` (StateChip)
 *   · agent count    → ABSENT from the payload → an honest dash, never invented
 */
const DASH = '—'

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
    <>
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full border-collapse text-body">
          <thead>
            <tr className="text-label uppercase text-ink-3">
              <th className="py-2 pr-4 text-left font-medium">Timestamp</th>
              <th className="py-2 pr-4 text-left font-medium">Question</th>
              <th className="py-2 pr-4 text-left font-medium">Documents used</th>
              <th className="py-2 pr-4 text-left font-medium">Status</th>
              <th className="tnum py-2 text-right font-medium">Agents</th>
            </tr>
          </thead>
          <tbody className="text-ink-2">
            {runs.map((run) => (
              <tr key={run.run_id} className="border-t border-ink-4 transition-colors hover:bg-survey-paper-2">
                <td className="tnum py-2.5 pr-4 font-measurement text-mono text-ink-3">{fmtDate(run.created_at)}</td>
                <td className="max-w-[360px] py-2.5 pr-4">
                  <Link to={`/runs/${run.run_id}`} className="block truncate text-ink hover:text-datum">
                    {run.query}
                  </Link>
                </td>
                <td className="py-2.5 pr-4 font-measurement text-mono text-ink-3">{truncateId(run.dataset_id, 8, 4)}</td>
                <td className="py-2.5 pr-4">
                  <StateChip state={run.status} />
                </td>
                <td className="tnum py-2.5 text-right font-measurement text-mono text-ink-3">{DASH}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Under md the timeline collapses to stacked cards (§6 responsive). */}
      <ul className="space-y-2 md:hidden">
        {runs.map((run) => (
          <li key={run.run_id} className="border-t border-ink-4 pt-3">
            <div className="flex items-start justify-between gap-3">
              <Link to={`/runs/${run.run_id}`} className="text-body text-ink hover:text-datum">
                {run.query}
              </Link>
              <StateChip state={run.status} />
            </div>
            <dl className="mt-2 grid grid-cols-3 gap-2 text-micro">
              <div>
                <dt className="text-ink-3">When</dt>
                <dd className="tnum font-measurement text-mono text-ink-2">{fmtDate(run.created_at)}</dd>
              </div>
              <div>
                <dt className="text-ink-3">Documents</dt>
                <dd className="font-measurement text-mono text-ink-2">{truncateId(run.dataset_id, 8, 4)}</dd>
              </div>
              <div>
                <dt className="text-ink-3">Agents</dt>
                <dd className="tnum font-measurement text-mono text-ink-2">{DASH}</dd>
              </div>
            </dl>
          </li>
        ))}
      </ul>
    </>
  )
}
