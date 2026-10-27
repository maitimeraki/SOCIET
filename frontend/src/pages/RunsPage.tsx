import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listRunsPage } from '../api/rest'
import type { RunSummary } from '../api/types'
import { buttonClasses } from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import ErrorState from '../components/ui/ErrorState'
import Skeleton from '../components/ui/Skeleton'
import { StateChip } from '../components/ui/Chip'
import PositionMark from '../components/ui/PositionMark'
import { PAGE_SIZE } from './pageSize'
import { fmtDate } from '../utils/format'

export interface RunsPageViewProps {
  runs: RunSummary[]
  loading: boolean
  failed: boolean
  failDetail?: string
  hasMore: boolean
  loadingMore: boolean
  onLoadMore: () => void
  onRetry: () => void
}

export function RunsPageView({
  runs,
  loading,
  failed,
  failDetail,
  hasMore,
  loadingMore,
  onLoadMore,
  onRetry,
}: RunsPageViewProps) {
  return (
    <div>
      <header className="flex flex-wrap items-end justify-between gap-4 pb-6">
        <div>
          <h1 className="font-titling text-display text-ink">Runs</h1>
          <p className="mt-2 max-w-[60ch] text-body text-ink-2">
            Every question you've brought, and how each one ended.
          </p>
        </div>
        <span className="font-measurement text-micro text-ink-3">{runs.length} TOTAL</span>
      </header>

      {failed ? (
        <ErrorState
          title="Couldn't reach the server"
          detail={failDetail || 'Your decisions load when the server is back.'}
          onRetry={onRetry}
          retryLabel="Try again"
        />
      ) : loading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((index) => (
            <Skeleton key={index} className="h-14 w-full" />
          ))}
        </div>
      ) : runs.length === 0 ? (
        <EmptyState
          line="No decisions yet. Every question you bring is listed here, with how it ended."
          action={
            <Link to="/new" className={buttonClasses('primary', 40, 'min-h-11')}>
              New decision
            </Link>
          }
        />
      ) : (
        <ul>
          {runs.map((entry) => {
            const stillGoing = entry.status === 'running' || entry.status === 'queued'
            return (
              <li key={entry.run_id}>
                <Link
                  to={`/runs/${entry.run_id}`}
                  className="flex items-start justify-between gap-4 border-b border-rule/40 py-3 hover:bg-ground-2"
                >
                  <span className="min-w-0">
                    <span className="block text-heading text-ink">{entry.query}</span>
                    <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 font-measurement text-micro text-ink-3">
                      {entry.verdict_stance ? (
                        <PositionMark position={entry.verdict_stance} ground="light" />
                      ) : (
                        <span>{stillGoing ? 'still running' : 'No outcome yet'}</span>
                      )}
                      <span>{fmtDate(entry.created_at)}</span>
                      <span>
                        {entry.rounds_executed} {entry.rounds_executed === 1 ? 'pass' : 'passes'}
                      </span>
                      <span>{entry.corpus_label ?? '—'}</span>
                    </span>
                  </span>
                  <StateChip state={entry.status} />
                </Link>
              </li>
            )
          })}
        </ul>
      )}

      {hasMore && (
        <div className="mt-4 flex justify-center">
          <button
            type="button"
            onClick={onLoadMore}
            disabled={loadingMore}
            className={buttonClasses('secondary', 40, 'min-h-11')}
          >
            {loadingMore ? 'Loading…' : 'Load more'}
          </button>
        </div>
      )}
    </div>
  )
}

export default function RunsPage() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    listRunsPage({ limit: PAGE_SIZE })
      .then((page) => {
        if (cancelled) return
        setRuns(page.items)
        setCursor(page.next_cursor)
        setFailed(false)
      })
      .catch(() => {
        if (cancelled) return
        // The server's raw text is not customer copy — the view's curated fallback renders instead.
        setFailed(true)
        setRuns([])
        setCursor(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [attempt])

  return (
    <RunsPageView
      runs={runs}
      loading={loading}
      failed={failed}
      hasMore={cursor !== null}
      loadingMore={loadingMore}
      onRetry={() => {
        setLoading(true)
        setFailed(false)
        setAttempt((value) => value + 1)
      }}
      onLoadMore={async () => {
        if (!cursor) return
        setLoadingMore(true)
        try {
          const page = await listRunsPage({ limit: PAGE_SIZE, cursor })
          setRuns((previous) => [...previous, ...page.items])
          setCursor(page.next_cursor)
        } catch {
          // A failed second page is the same recoverable failure as a failed first one.
          setFailed(true)
        } finally {
          setLoadingMore(false)
        }
      }}
    />
  )
}
