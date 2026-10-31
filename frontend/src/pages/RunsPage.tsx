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

export interface MonthGroup {
  label: string
  runs: RunSummary[]
}

/** The runs under their month, newest month first — the month label is a sticky caps label. */
// eslint-disable-next-line react-refresh/only-export-components -- groupByMonth is the tested grouping rule
export function groupByMonth(runs: RunSummary[]): MonthGroup[] {
  const groups = new Map<string, RunSummary[]>()
  for (const run of runs) {
    const key = run.created_at.slice(0, 7)
    const list = groups.get(key)
    if (list) list.push(run)
    else groups.set(key, [run])
  }
  return [...groups.entries()]
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([key, list]) => ({
      label: new Date(`${key}-01T00:00:00Z`).toLocaleDateString('en-GB', {
        month: 'long',
        year: 'numeric',
        timeZone: 'UTC',
      }),
      runs: list,
    }))
}

/** §7.5 — the filed outcome: position mark + word, then the share as a measurement. */
function Outcome({ run }: { run: RunSummary }) {
  if (!run.verdict_stance) {
    return <span className="font-mono text-micro text-ink-3">—</span>
  }
  return (
    <span className="flex items-center gap-2">
      <PositionMark position={run.verdict_stance} size="sm" ground="light" />
      <span className="font-mono text-micro text-ink-3">
        {run.verdict_confidence === null ? '—' : run.verdict_confidence.toFixed(2)}
      </span>
    </span>
  )
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
  const groups = groupByMonth(runs)

  return (
    <div>
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-rule pb-6">
        <div>
          <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Runs</p>
          <h1 className="font-display text-display font-medium tracking-[-0.03em] text-ink">Your decisions</h1>
          <p className="mt-2 max-w-[60ch] font-ui text-body-sm text-ink-2">Every question you have put to a panel.</p>
        </div>
        <Link to="/new" className={buttonClasses('primary', 48, 'min-h-11')}>
          New decision
        </Link>
      </header>

      {failed && runs.length === 0 ? (
        <div className="mt-6">
          <ErrorState
            title="Couldn't reach the server"
            detail={failDetail || 'Your decisions load when the server is back.'}
            onRetry={onRetry}
            retryLabel="Try again"
          />
        </div>
      ) : loading ? (
        <div className="mt-6 space-y-2">
          {[0, 1, 2, 3, 4, 5].map((index) => (
            <Skeleton key={index} className="h-[52px] w-full" />
          ))}
        </div>
      ) : runs.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            line="No decisions yet. Ask the first one."
            action={
              <Link to="/new" className={buttonClasses('primary', 40, 'min-h-11')}>
                Start a decision
              </Link>
            }
          />
        </div>
      ) : (
        <div className="mt-4">
          {groups.map((group) => (
            <section key={group.label}>
              <h2 className="sticky top-0 z-10 border-b border-rule bg-bone py-2 font-ui text-label uppercase tracking-[0.09em] text-ink-3">
                {group.label}
              </h2>
              <ul>
                {group.runs.map((entry) => (
                  <li key={entry.run_id}>
                    <Link
                      to={`/runs/${entry.run_id}`}
                      className="group flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-rule/40 py-3 hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent xl:grid xl:grid-cols-[minmax(0,1fr)_7rem_4rem_7.5rem_8rem_2.5rem]"
                    >
                      <span className="w-full min-w-0 font-ui text-body text-ink xl:w-auto">{entry.query}</span>
                      <span>
                        <StateChip state={entry.status} />
                      </span>
                      <span className="font-mono text-mono text-ink-3">pass {entry.rounds_executed}</span>
                      <span className="font-mono text-mono text-ink-3">{fmtDate(entry.created_at)}</span>
                      <Outcome run={entry} />
                      <span
                        aria-hidden="true"
                        className="ml-auto font-mono text-micro text-ink-3 underline underline-offset-4 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
                      >
                        Open
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      {failed && runs.length > 0 && (
        <div role="alert" className="mt-4 flex flex-wrap items-center justify-center gap-3">
          <span className="font-ui text-body-sm text-ink-2">Couldn't load more.</span>
          <button type="button" onClick={onLoadMore} className={buttonClasses('secondary', 40, 'min-h-11')}>
            Try again
          </button>
        </div>
      )}

      {hasMore && !failed && (
        <div className="mt-4 flex justify-center">
          <button
            type="button"
            onClick={onLoadMore}
            disabled={loadingMore}
            className={buttonClasses('ghost', 40, 'min-h-11')}
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
          setFailed(false)
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
