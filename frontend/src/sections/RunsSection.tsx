import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listRuns } from '../api/rest'
import type { RunSummary } from '../api/types'
import Button, { buttonClasses } from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import ErrorState from '../components/ui/ErrorState'
import Skeleton from '../components/ui/Skeleton'
import RunTable from '../components/common/RunTable'

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

export interface RunsViewProps {
  runs: RunSummary[]
  loading: boolean
  failed: boolean
  /** The server's own failure message, when there is one; the standing copy stands in otherwise. */
  failDetail?: string
  onRetry: () => void
}

/**
 * §8.4 Decisions — the process of each decision: when it ran, the question, the corpus, the passes
 * completed, the outcome and the status. Presentational: the data and the retry arrive as props (the
 * default export owns the fetch), so this renders under `react-dom/server` in the node-only suite
 * where `useEffect` never fires. D16: the label ("Decisions") and the path (`/runs`) differ on purpose.
 */
export function RunsView({ runs, loading, failed, failDetail, onRetry }: RunsViewProps) {
  return (
    <div className="space-y-6">
      <h1 className="font-titling text-display text-ink">Decisions</h1>
      {failed ? (
        // A failure is never an empty list: it is surfaced, with a retry.
        <ErrorState
          title="Couldn't reach the server"
          detail={failDetail || 'Your decisions load when the server is back.'}
          actions={
            <Button type="button" variant="secondary" onClick={onRetry}>
              Try again
            </Button>
          }
        />
      ) : loading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : runs.length === 0 ? (
        <EmptyState
          line="No decisions yet. Every decision you start — the question, its passes and how it ended — is listed here."
          action={
            <Link to="/new/ingest" className={buttonClasses('primary', 40)}>
              Start a decision
            </Link>
          }
        />
      ) : (
        <RunTable runs={runs} />
      )}
    </div>
  )
}

/**
 * The section's container: it owns the fetch and the retry counter the view never sees. Bumping
 * `attempt` re-runs the effect — the retry affordance without a second code path.
 */
export default function RunsSection() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [failDetail, setFailDetail] = useState<string>()
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    listRuns()
      .then((items) => {
        if (cancelled) return
        setRuns(items)
        setFailed(false)
        setFailDetail(undefined)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setFailed(true)
        setFailDetail(error instanceof Error ? error.message : undefined)
        setRuns([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [attempt])

  const retry = () => {
    setLoading(true)
    setFailed(false)
    setFailDetail(undefined)
    setAttempt((n) => n + 1)
  }

  return <RunsView runs={runs} loading={loading} failed={failed} failDetail={failDetail} onRetry={retry} />
}
