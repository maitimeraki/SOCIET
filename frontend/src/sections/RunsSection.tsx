import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listRunsPage } from '../api/rest'
import type { RunSummary } from '../api/types'
import Button, { buttonClasses } from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import ErrorState from '../components/ui/ErrorState'
import { toast } from '../components/ui/Toast'
import { DASHBOARD_COPY } from '../pages/dashboardCopy'
import RunTable from '../components/common/RunTable'

type StatusFilter = 'all' | 'complete' | 'running' | 'failed' | 'interrupted'

/**
 * The list's client-side filter — pure, so it is testable without a DOM (this suite is node-only).
 *
 * Relocated here from the retired `pages/RunsPage.tsx` together with its coverage (Ruling F4): the
 * filter travels with the section that owns the decisions list.
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

/** The v1 page size: the first keyset page of 25, then Load more walks `next_cursor`. */
const PAGE_SIZE = 25

export interface RunsViewProps {
  runs: RunSummary[]
  loading: boolean
  failed: boolean
  /** The server's own failure message, when there is one; the standing copy stands in otherwise. */
  failDetail?: string
  hasMore: boolean
  loadingMore: boolean
  onLoadMore: () => void
  onRetry: () => void
}

/**
 * Your decisions (§14.3) — the question-led cards, newest first, each linking to its decision.
 * The section owns the keyset walk: the first page, then Load more over `next_cursor` (§12.4
 * Wave B). The heading lives on the dashboard, so this renders its content only.
 */
export function RunsView({
  runs,
  loading,
  failed,
  failDetail,
  hasMore,
  loadingMore,
  onLoadMore,
  onRetry,
}: RunsViewProps) {
  return (
    <div className="mt-6">
      {failed ? (
        // A failure is never an empty list: it is surfaced, with a retry.
        <ErrorState
          title={DASHBOARD_COPY.error.title}
          detail={failDetail || DASHBOARD_COPY.error.decisions}
          onRetry={onRetry}
          retryLabel={DASHBOARD_COPY.actions.retry}
        />
      ) : loading ? (
        <RunTable runs={[]} loading />
      ) : runs.length === 0 ? (
        <EmptyState
          line={DASHBOARD_COPY.empty.decisions}
          action={
            <Link to="/new" className={buttonClasses('primary', 40, 'min-h-11')}>
              {DASHBOARD_COPY.startFree}
            </Link>
          }
        />
      ) : (
        <>
          <RunTable runs={runs} />
          {hasMore && (
            <div className="mt-4 flex justify-center">
              <Button onClick={onLoadMore} loading={loadingMore} className="min-h-11">
                {DASHBOARD_COPY.actions.loadMore}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export interface RunsSectionProps {
  /** Bumped by the dashboard when any section's retry asks the page to refresh. */
  refreshKey?: number
  /** The page's refresh; when absent the section retries on its own. */
  onRefresh?: () => void
}

/**
 * The section's container: it owns the fetch, the keyset cursor and the retry the view never sees.
 * A retry either bumps the page's refresh key (one refresh for the whole surface) or, standalone,
 * this section's own attempt.
 */
export default function RunsSection({ refreshKey = 0, onRefresh }: RunsSectionProps = {}) {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [failed, setFailed] = useState(false)
  const [failDetail, setFailDetail] = useState<string>()
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    listRunsPage({ limit: PAGE_SIZE })
      .then((page) => {
        if (cancelled) return
        setRuns(page.items)
        setCursor(page.next_cursor)
        setFailed(false)
        setFailDetail(undefined)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setFailed(true)
        setFailDetail(error instanceof Error ? error.message : undefined)
        setRuns([])
        setCursor(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [attempt, refreshKey])

  const loadMore = async () => {
    if (!cursor) return
    setLoadingMore(true)
    try {
      const page = await listRunsPage({ limit: PAGE_SIZE, cursor })
      setRuns((previous) => [...previous, ...page.items])
      setCursor(page.next_cursor)
    } catch (error) {
      toast('error', error instanceof Error ? error.message : "Couldn't load more decisions")
    } finally {
      setLoadingMore(false)
    }
  }

  const retry = () => {
    setLoading(true)
    setFailed(false)
    setFailDetail(undefined)
    if (onRefresh) onRefresh()
    else setAttempt((n) => n + 1)
  }

  return (
    <RunsView
      runs={runs}
      loading={loading}
      failed={failed}
      failDetail={failDetail}
      hasMore={cursor !== null}
      loadingMore={loadingMore}
      onLoadMore={loadMore}
      onRetry={retry}
    />
  )
}
