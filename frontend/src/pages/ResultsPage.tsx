import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getRun, listRunsPage } from '../api/rest'
import type { RunSummary } from '../api/types'
import type { Stance } from '../run/events'
import { reportFromState } from '../components/run/reportFromState'
import type { ReportModel } from '../components/run/exportReport'
import ReportDocument from '../components/run/ReportDocument'
import Button, { buttonClasses } from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import ErrorState from '../components/ui/ErrorState'
import Skeleton from '../components/ui/Skeleton'
import PositionMark from '../components/ui/PositionMark'
import { applyStoredResult, fold } from '../run/reducer'
import { PAGE_SIZE } from './pageSize'
import { fmtDay } from '../utils/format'

export interface VerdictRow {
  runId: string
  question: string
  stance: Stance
  share: number | null
  date: string
}

export interface VerdictsPageViewProps {
  latest: { runId: string; report: ReportModel } | null
  earlier: VerdictRow[]
  loading: boolean
  failed: boolean
  failDetail?: string
  onRetry: () => void
  /** A retried report was written: the page reads its verdicts again. Resolves once the reload has landed. */
  onRestored: () => Promise<void>
}

export function VerdictsPageView({ latest, earlier, loading, failed, failDetail, onRetry, onRestored }: VerdictsPageViewProps) {
  return (
    <div>
      {/* §7.6/§12.7 — the outcome is the first thing; the page's name is for the document outline only. */}
      <h1 className="sr-only font-display">Verdicts</h1>

      {failed ? (
        <ErrorState
          title="Couldn't reach the server"
          detail={failDetail || 'Your verdicts load when the server is back.'}
          onRetry={onRetry}
          retryLabel="Try again"
        />
      ) : loading ? (
        <Skeleton className="h-64 w-full" />
      ) : latest ? (
        <div className="grid gap-6 lg:grid-cols-12 print:block">
          <div className="lg:col-span-8 print:block">
            <ReportDocument report={latest.report} runId={latest.runId} onRestored={onRestored} />
            {latest.report.reportStatus === 'produced' ? (
              <Button variant="ghost" className="mt-6 print:hidden" onClick={() => window.print()}>
                Export document
              </Button>
            ) : null}
          </div>
          <aside className="lg:col-span-4 print:hidden">
            <h2 className="mb-2 font-ui text-label uppercase tracking-[0.09em] text-ink-3">
              Earlier answers <span className="font-mono text-micro text-ink-3">{earlier.length}</span>
            </h2>
            <div>
              {earlier.map((row) => (
                <Link
                  key={row.runId}
                  to={`/runs/${row.runId}/verdict`}
                  className="flex flex-col gap-1 border-t border-rule py-3 hover:bg-accent-soft"
                >
                  <span className="font-ui text-body-sm font-medium text-ink">{row.question}</span>
                  <span className="flex items-center justify-between gap-3">
                    <span className="font-mono text-micro text-ink-3">{fmtDay(row.date)}</span>
                    <span className="flex items-center gap-3">
                      <PositionMark position={row.stance} size="sm" ground="light" />
                      <span className="tnum font-mono text-micro text-ink-2">
                        {row.share === null ? '—' : row.share.toFixed(2)}
                      </span>
                    </span>
                  </span>
                </Link>
              ))}
            </div>
          </aside>
        </div>
      ) : (
        <EmptyState
          line="Your first answer appears here when a decision files one."
          action={
            <Link to="/new" className={buttonClasses('primary', 40, 'min-h-11')}>
              New decision
            </Link>
          }
        />
      )}
    </div>
  )
}

/** The most answered runs whose documents the headline probe reads. */
const HEADLINE_PROBE_LIMIT = 5

// eslint-disable-next-line react-refresh/only-export-components -- loadVerdicts is the tested loader
export async function loadVerdicts() {
  const answered: RunSummary[] = []
  let cursor: string | null = null
  do {
    const page = await listRunsPage({ limit: PAGE_SIZE, cursor })
    answered.push(...page.items.filter((entry) => entry.verdict_stance))
    cursor = page.next_cursor
  } while (cursor && answered.length < 50)

  // The headline probe reads the documents of at most the first HEADLINE_PROBE_LIMIT answered runs,
  // one at a time. It stops at the first produced report; otherwise it headlines the first readable
  // run, which may be one whose report was not produced. Every row of the archive, probed or not,
  // takes its stance, share and date from the list, so the page never waits on more than the probe
  // and one unreadable run (deleted, 404, transient 5xx) never blanks the archive.
  // §11.3 — the sheet is the same `reportFromState` construction the run page renders and every
  // export serializes; the page never re-derives the reasoning or the sources.
  let latest: VerdictsPageViewProps['latest'] = null
  for (const entry of answered.slice(0, HEADLINE_PROBE_LIMIT)) {
    try {
      const doc = await getRun(entry.run_id)
      const report = reportFromState(applyStoredResult(fold(doc.events), doc.result))
      if (!report) continue
      if (report.reportStatus === 'produced') {
        latest = { runId: entry.run_id, report }
        break
      }
      latest ??= { runId: entry.run_id, report }
    } catch (error) {
      // Diagnosable without leaking the server's text into the page.
      console.error('ResultsPage: could not read one verdict.', error)
    }
  }

  const earlier: VerdictRow[] = answered
    .filter((row) => row.run_id !== latest?.runId)
    .map((row) => ({
      runId: row.run_id,
      question: row.query,
      stance: row.verdict_stance as Stance,
      share: row.verdict_confidence,
      date: row.created_at,
    }))

  return { latest, earlier }
}

export default function ResultsPage() {
  const [data, setData] = useState<{ latest: VerdictsPageViewProps['latest']; earlier: VerdictRow[] }>({
    latest: null,
    earlier: [],
  })
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    loadVerdicts()
      .then((loaded) => {
        if (cancelled) return
        setData(loaded)
        setFailed(false)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        // The server's raw text is not customer copy — the view's curated fallback renders instead.
        console.error('ResultsPage: could not load verdicts.', error)
        setFailed(true)
        setData({ latest: null, earlier: [] })
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [attempt])

  // A retry wrote a report: read the archive again, and keep the page as it was if the read fails.
  const refreshVerdicts = async () => {
    try {
      setData(await loadVerdicts())
    } catch (error) {
      console.error('ResultsPage: could not reload verdicts.', error)
    }
  }

  return (
    <VerdictsPageView
      latest={data.latest}
      earlier={data.earlier}
      loading={loading}
      failed={failed}
      onRetry={() => {
        setLoading(true)
        setFailed(false)
        setAttempt((value) => value + 1)
      }}
      onRestored={refreshVerdicts}
    />
  )
}
