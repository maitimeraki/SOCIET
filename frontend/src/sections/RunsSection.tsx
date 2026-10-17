import { Link } from 'react-router-dom'
import type { RunSummary } from '../api/types'
import EmptyState from '../components/ui/EmptyState'
import { buttonClasses } from '../components/ui/Button'

type StatusFilter = 'all' | 'complete' | 'running' | 'failed' | 'interrupted'

/**
 * The list's client-side filter — pure, so it is testable without a DOM (this suite is node-only).
 *
 * Relocated here from the retired `pages/RunsPage.tsx` together with its coverage (Ruling F4): the
 * filter travels with the section that owns the runs list, which is what repointing `/runs` retires.
 */
// eslint-disable-next-line react-refresh/only-export-components -- filterRuns is the section's pure filter, shared with its test
export function filterRuns(runs: RunSummary[], status: StatusFilter, text: string): RunSummary[] {
  const needle = text.trim().toLowerCase()
  return runs.filter((run) => {
    const statusOk =
      status === 'all' ||
      (status === 'running' ? run.status === 'running' || run.status === 'queued' : run.status === status)
    const textOk = needle.length === 0 || run.query.toLowerCase().includes(needle)
    return statusOk && textOk
  })
}

/**
 * §8.4 Decisions — the process of each decision: when, the question, and the status, where the
 * Verdicts section shows the outcome. The label and the path deliberately differ (D16): "Decisions" is
 * customer copy, `/runs` is an internal identifier exempt from the copy law (§13).
 *
 * An honest placeholder: it states the section's purpose and its one next action. The question-led
 * list lands in this section's own task, so nothing here pretends a decision exists.
 */
export default function RunsSection() {
  return (
    <div className="space-y-6">
      <h1 className="font-titling text-display text-ink">Decisions</h1>
      <EmptyState
        line="No decisions yet. Every decision you start — the question, its passes and how it ended — is listed here."
        action={
          <Link to="/new/ingest" className={buttonClasses('primary', 40)}>
            Start a decision
          </Link>
        }
      />
    </div>
  )
}
