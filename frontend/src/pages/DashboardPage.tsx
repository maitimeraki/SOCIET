import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listRunsPage } from '../api/rest'
import type { RunSummary } from '../api/types'
import ChamberFloor from '../components/chamber/ChamberFloor'
import { toast } from '../components/ui/Toast'
import { useRunStore } from '../run/runStore'
import { useDraftStore } from '../wizard/draftStore'
import DashboardView from './dashboardView'

/** The v1 page size (plan §6): one keyset page of 25, then Load more walks `next_cursor`. */
const PAGE_SIZE = 25

/** The newest run still on the floor — the inset's subject; null when nothing is deliberating. */
function liveRun(runs: RunSummary[]): RunSummary | null {
  return runs.find((run) => run.status === 'running') ?? null
}

/**
 * The live-debate inset (plan §3.3). It drives the same `ChamberFloor` and the same run store the
 * full `/runs/:runId` view uses — one subscription for the one live run, never one per timeline row —
 * so the inset is bounded exactly as the full view is: the floor is bounded by the roster (≤
 * `max_agents`), and its seat arcs reuse the chamber's existing geometry. Hidden below `lg`; the
 * heading links to the run.
 *
 * Not `GraphCanvas`: that surface streams `/api/v1/simulate/{id}/graph_stream`, which resolves a
 * *job* doc to a dataset snapshot — a debate run is a run, not a graph job, and the dashboard holds no
 * graph job id — so the running debate's graph is the floor, not the corpus graph.
 */
function LiveInset({ run }: { run: RunSummary }) {
  const roster = useRunStore((s) => s.run.roster)
  const rounds = useRunStore((s) => s.run.rounds)
  const livePairs = useRunStore((s) => s.run.livePairs)
  const loadAndConnect = useRunStore((s) => s.loadAndConnect)
  const disconnect = useRunStore((s) => s.disconnect)

  useEffect(() => {
    void loadAndConnect(run.run_id)
    return () => disconnect()
  }, [run.run_id, loadAndConnect, disconnect])

  return (
    <section className="border-y border-ink-4 py-3">
      <header className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-heading text-ink">Debating now</h2>
        <Link to={`/runs/${run.run_id}`} className="text-body text-ink-2 hover:text-accent">
          Open the run →
        </Link>
      </header>
      <p className="mb-3 truncate text-body text-ink-2">{run.query}</p>
      <div className="hidden lg:block">
        <ChamberFloor roster={roster} rounds={rounds} activeRound={null} livePairs={livePairs} />
      </div>
    </section>
  )
}

/**
 * The operate home (plan §3.3). It owns the data flow — the first keyset page, Load more over
 * `next_cursor`, the wizard's corpus for the primary action — and the live inset; the presentation
 * lives in `dashboardView`, which the node-only suite renders directly.
 */
export default function DashboardPage() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [failed, setFailed] = useState(false)
  // The server's own message, forwarded so the failure state is never silent (CLAUDE.md: never
  // swallow exceptions). Absent (a non-Error throw) the view falls back to its standing copy.
  const [failDetail, setFailDetail] = useState<string>()
  // The client's own corpus knowledge: the wizard draft (sessionStorage). Absent in a fresh session,
  // so the primary action defaults to the ingest step.
  const datasetId = useDraftStore((s) => s.datasetId)

  useEffect(() => {
    listRunsPage({ limit: PAGE_SIZE })
      .then((page) => {
        setRuns(page.items)
        setCursor(page.next_cursor)
      })
      .catch((error: unknown) => {
        setFailed(true)
        setFailDetail(error instanceof Error ? error.message : undefined)
      })
      .finally(() => setLoading(false))
  }, [])

  const loadMore = async () => {
    if (!cursor) return
    setLoadingMore(true)
    try {
      const page = await listRunsPage({ limit: PAGE_SIZE, cursor })
      setRuns((previous) => [...previous, ...page.items])
      setCursor(page.next_cursor)
    } catch (error) {
      toast('error', error instanceof Error ? error.message : "Couldn't load more runs")
    } finally {
      setLoadingMore(false)
    }
  }

  const live = liveRun(runs)

  return (
    <DashboardView
      runs={runs}
      loading={loading}
      failed={failed}
      failDetail={failDetail}
      hasMore={cursor !== null}
      loadingMore={loadingMore}
      onLoadMore={loadMore}
      datasetReady={datasetId !== null}
      liveInset={live ? <LiveInset run={live} /> : undefined}
    />
  )
}
