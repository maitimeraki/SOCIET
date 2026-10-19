import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { RunSummary } from '../api/types'
// Imported by path, not through the `../components/ui` barrel: the barrel also re-exports Dialog and
// Drawer, whose framer-motion import would otherwise ride into this module — and this module is what
// the node-only dashboard test renders (R45: framer-motion in a test is a measured cost).
import RunTable from '../components/common/RunTable'
import Button, { buttonClasses } from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import ErrorState from '../components/ui/ErrorState'

export interface DashboardViewProps {
  runs: RunSummary[]
  loading: boolean
  failed: boolean
  /** The server's own failure message, when the page has one; the standing copy stands in otherwise. */
  failDetail?: string
  hasMore: boolean
  loadingMore: boolean
  onLoadMore: () => void
  /** True when the client still holds the wizard's corpus — the primary action then skips ingest. */
  datasetReady: boolean
  /** The live-debate inset, injected by the page so this module stays free of the graph stack. */
  liveInset?: ReactNode
}

/**
 * The operate home (plan §3.3), presentational: the title block, the primary action, the traverse log
 * (the run timeline) and the honest empty state. The data and the live inset arrive as props, so this
 * renders under `react-dom/server` in the node-only suite without dragging in the graph stack.
 *
 * The timeline is `RunTable` — the plan's own instruction ("reuse `RunTable.tsx` and extend its
 * columns", §3.3) — so the dashboard and `/runs` render the same columns from one component.
 */
export default function DashboardView({
  runs,
  loading,
  failed,
  failDetail,
  hasMore,
  loadingMore,
  onLoadMore,
  datasetReady,
  liveInset,
}: DashboardViewProps) {
  const startTarget = datasetReady ? '/new/society' : '/new/ingest'
  const empty = !loading && !failed && runs.length === 0

  return (
    <div className="space-y-10">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-label uppercase text-ink-3">Operate</p>
          <h1 className="mt-2 font-titling text-display text-ink">The traverse log</h1>
          <p className="mt-2 max-w-[60ch] text-body text-ink-2">
            Every run your society has deliberated, newest first.
          </p>
        </div>
        <Link to={startTarget} className={buttonClasses('primary')}>
          Start a Society
        </Link>
      </header>

      {liveInset}

      <section>
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="text-heading text-ink">Recent runs</h2>
          <Link to="/runs" className="text-body text-ink-2 hover:text-accent">
            All runs →
          </Link>
        </div>

        {failed ? (
          <ErrorState
            title="Couldn't reach the server"
            detail={failDetail || 'The traverse log loads when the server is back.'}
          />
        ) : empty ? (
          <EmptyState
            line="No runs yet — the log fills the moment your first society deliberates."
            action={
              <Link to={startTarget} className={buttonClasses('primary', 40)}>
                Run your first society
              </Link>
            }
          />
          // TODO(Task 17): the demo video lands here, inside the first-run empty state (plan §3.3).
        ) : (
          <>
            <RunTable runs={runs} loading={loading} />
            {hasMore && (
              <div className="mt-4 flex justify-center">
                <Button onClick={onLoadMore} loading={loadingMore}>
                  Load more
                </Button>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  )
}
