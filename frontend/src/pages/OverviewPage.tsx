import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getRun, listRunsPage, listUploads } from '../api/rest'
import type { RunSummary, UploadRow } from '../api/types'
import StatsBand from '../components/overview/StatsBand'
import RecentWork from '../components/overview/RecentWork'
import type { RecentRow } from '../components/overview/RecentWork'
import YourMaterial from '../components/overview/YourMaterial'
import { corpusRows } from '../components/overview/corpusRows'
import type { CorpusRow } from '../components/overview/corpusRows'
import PlanUsage from '../components/overview/PlanUsage'
import WorkingNow from '../components/overview/WorkingNow'
import type { WorkingRun } from '../components/overview/WorkingNow'
import { buttonClasses } from '../components/ui/Button'
import ErrorState from '../components/ui/ErrorState'
import Skeleton from '../components/ui/Skeleton'

/** The plan the account is on. Placeholder figures — the plan is a studio plan. */
const CORPUS_LIMIT = 2_000_000_000
const DECISIONS_LIMIT = 20

/** `YYYY-MM` in UTC — the month the page measures, taken from the clock, never a literal. */
// eslint-disable-next-line react-refresh/only-export-components -- monthKeyUtc is the tested clock rule
export function monthKeyUtc(date: Date): string {
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`
}

export interface OverviewStats {
  decisions: number
  filed: number
  corpusBytes: number
  corpusLimit: number
  decisionsLeft: number
  decisionsLimit: number
}

export interface OverviewPageViewProps {
  stats: OverviewStats
  recent: RecentRow[]
  corpora: CorpusRow[]
  working: WorkingRun | null
  loading: boolean
  failed: boolean
  onRetry: () => void
}

export function OverviewPageView({ stats, recent, corpora, working, loading, failed, onRetry }: OverviewPageViewProps) {
  const today = new Date().toLocaleDateString('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    timeZone: 'UTC',
  })
  // §14.2 — the state line is honest: it reads the live filed count, never a fixed number.
  const stateLine = working
    ? `One question is with the panel.${stats.filed > 0 ? ` ${stats.filed} filed and waiting for you.` : ' Nothing is filed yet.'}`
    : `Nothing is running.${stats.filed > 0 ? ` ${stats.filed} answer${stats.filed === 1 ? '' : 's'} filed and waiting for you.` : ' Nothing is filed yet.'}`
  return (
    <div className="bg-[image:var(--gradient-morning)] bg-no-repeat">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-rule pb-6">
        <div>
          <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">{today}</p>
          <h1 className="font-display text-display font-medium tracking-[-0.03em] text-ink">Good morning, Anupam.</h1>
          <p className="mt-2 max-w-[52ch] font-ui text-body-sm text-ink-2">{stateLine}</p>
        </div>
        <div className="flex items-center gap-4">
          <Link to="/runs" className="font-ui text-body-sm text-ink-2 underline underline-offset-4 hover:text-ink">
            View all decisions
          </Link>
          <Link to="/new" className={buttonClasses('primary', 48, 'min-h-11')}>
            New decision
          </Link>
        </div>
      </header>

      {failed ? (
        <div className="mt-6">
          <ErrorState
            title="Couldn't reach the server"
            detail="Your overview loads when the server is back."
            onRetry={onRetry}
            retryLabel="Try again"
          />
        </div>
      ) : loading ? (
        <div className="mt-6 space-y-4">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-56 w-full" />
        </div>
      ) : (
        <div className="mt-6 grid grid-cols-1 items-start gap-7 lg:grid-cols-[minmax(0,1.6fr)_minmax(300px,0.75fr)]">
          <div>
            <StatsBand
              decisions={stats.decisions}
              filed={stats.filed}
              corpusBytes={stats.corpusBytes}
              corpusLimit={stats.corpusLimit}
              decisionsLeft={stats.decisionsLeft}
              decisionsLimit={stats.decisionsLimit}
            />
            <RecentWork rows={recent} />
            <YourMaterial rows={corpora} />
          </div>
          <aside className="grid gap-5">
            <PlanUsage
              corpusBytes={stats.corpusBytes}
              corpusLimit={stats.corpusLimit}
              decisionsUsed={stats.decisionsLimit - stats.decisionsLeft}
              decisionsLimit={stats.decisionsLimit}
              renews="1 Nov 2026"
            />
            <WorkingNow run={working} />
          </aside>
        </div>
      )}
    </div>
  )
}

/** The newest runs — the page measures the current month's share of them. */
async function loadRecentRuns(): Promise<RunSummary[]> {
  const page = await listRunsPage({ limit: 25 })
  return page.items
}

export default function OverviewPage() {
  const [stats, setStats] = useState<OverviewStats>({
    decisions: 0,
    filed: 0,
    corpusBytes: 0,
    corpusLimit: CORPUS_LIMIT,
    decisionsLeft: DECISIONS_LIMIT,
    decisionsLimit: DECISIONS_LIMIT,
  })
  const [recent, setRecent] = useState<RecentRow[]>([])
  const [corpora, setCorpora] = useState<CorpusRow[]>([])
  const [working, setWorking] = useState<WorkingRun | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    Promise.all([listUploads(), loadRecentRuns()])
      .then(async ([uploads, runs]) => {
        if (cancelled) return
        const items: UploadRow[] = uploads.items ?? []
        const corpusBytes = items.reduce((sum, item) => sum + item.bytes, 0)
        const month = monthKeyUtc(new Date())
        const monthRuns = runs.filter((run) => monthKeyUtc(new Date(run.created_at)) === month)
        const filed = monthRuns.filter((run) => run.verdict_stance).length
        const running = runs.find((run) => run.status === 'running' || run.status === 'queued')
        let live: WorkingRun | null = null
        if (running) {
          const doc = await getRun(running.run_id)
          if (cancelled) return
          live = {
            runId: running.run_id,
            question: running.query,
            passes: `${running.rounds_executed} of ${doc.config.max_rounds}`,
            note: `Pass ${running.rounds_executed} of ${doc.config.max_rounds}.`,
            convergence: null,
          }
        }
        setStats({
          decisions: monthRuns.length,
          filed,
          corpusBytes,
          corpusLimit: CORPUS_LIMIT,
          decisionsLeft: Math.max(0, DECISIONS_LIMIT - monthRuns.length),
          decisionsLimit: DECISIONS_LIMIT,
        })
        setRecent(
          monthRuns.slice(0, 4).map((run) => ({
            runId: run.run_id,
            question: run.query,
            state: run.verdict_stance ? 'Filed' : 'Deliberating',
            stance: run.verdict_stance,
            share: run.verdict_confidence,
            passes: `${run.rounds_executed} of 5`,
            date: run.created_at.slice(0, 10),
          })),
        )
        setCorpora(corpusRows(items, runs))
        setWorking(live)
        setFailed(false)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        console.error('OverviewPage: could not load the overview.', error)
        setFailed(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [attempt])

  return (
    <OverviewPageView
      stats={stats}
      recent={recent}
      corpora={corpora}
      working={working}
      loading={loading}
      failed={failed}
      onRetry={() => {
        setLoading(true)
        setFailed(false)
        setAttempt((value) => value + 1)
      }}
    />
  )
}
