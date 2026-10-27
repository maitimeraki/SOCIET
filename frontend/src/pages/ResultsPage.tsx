import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getRun, listRunsPage } from '../api/rest'
import type { RunSummary } from '../api/types'
import type { Stance } from '../run/events'
import AnswerDocument, { sourceTitles } from '../components/run/AnswerDocument'
import { buttonClasses } from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import ErrorState from '../components/ui/ErrorState'
import Skeleton from '../components/ui/Skeleton'
import PositionMark from '../components/ui/PositionMark'
import { fold } from '../run/reducer'
import { verdictView } from '../run/selectors'
import type { VerdictView } from '../run/selectors'
import { PAGE_SIZE } from './pageSize'
import { fmtDate } from '../utils/format'

export interface VerdictRow {
  runId: string
  question: string
  stance: Stance
  share: number | null
  date: string
}

export interface VerdictsPageViewProps {
  latest: { runId: string; question: string; view: VerdictView; sources: string[]; corpusMissing: boolean } | null
  earlier: VerdictRow[]
  loading: boolean
  failed: boolean
  failDetail?: string
  onRetry: () => void
}

export function VerdictsPageView({ latest, earlier, loading, failed, failDetail, onRetry }: VerdictsPageViewProps) {
  return (
    <div>
      <header className="flex flex-wrap items-end justify-between gap-4 pb-6">
        <div>
          <h1 className="font-titling text-display text-ink">Verdicts</h1>
          <p className="mt-2 max-w-[60ch] text-body text-ink-2">
            The final answer to every question you've brought.
          </p>
        </div>
        <span className="font-measurement text-micro text-ink-3">{earlier.length + (latest ? 1 : 0)} TOTAL</span>
      </header>

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
        <div className="grid gap-6 lg:grid-cols-12">
          <div className="lg:col-span-8">
            <AnswerDocument
              runId={latest.runId}
              question={latest.question}
              view={latest.view}
              sources={latest.sources}
              corpusMissing={latest.corpusMissing}
            />
          </div>
          <aside className="lg:col-span-4">
            <h2 className="mb-2 font-measurement text-micro text-ink-3">EARLIER VERDICTS</h2>
            <ul>
              {earlier.map((row) => (
                <li key={row.runId}>
                  <Link to={`/runs/${row.runId}/verdict`} className="grid grid-cols-[62px_1fr_auto] gap-3 border-b border-rule/30 py-2 hover:bg-ground-2">
                    <span className="font-measurement text-micro text-ink-3">{fmtDate(row.date)}</span>
                    <span className="text-body text-ink-2">{row.question}</span>
                    <span className="flex items-center gap-2">
                      <PositionMark position={row.stance} size="sm" ground="light" />
                      <span className="font-measurement text-mono text-ink-2">{row.share?.toFixed(2) ?? '—'}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
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

type LoadedVerdict = { entry: RunSummary; view: VerdictView; sources: string[] }

export async function loadVerdicts() {
  const answered: RunSummary[] = []
  let cursor: string | null = null
  do {
    const page = await listRunsPage({ limit: PAGE_SIZE, cursor })
    answered.push(...page.items.filter((entry) => entry.verdict_stance))
    cursor = page.next_cursor
  } while (cursor && answered.length < 50)

  // One document read per answered run: the same folded roster answers both the verdict and its sources.
  // Settled, not all: one unreadable run (deleted, 404, transient 5xx) must not blank the whole archive.
  const results = await Promise.allSettled(
    answered.slice(0, 50).map(async (entry) => {
      const doc = await getRun(entry.run_id)
      const state = fold(doc.events)
      const view = verdictView(state)
      return view ? { entry, view, sources: sourceTitles(state.roster) } : null
    }),
  )
  const loaded: LoadedVerdict[] = []
  for (const result of results) {
    if (result.status === 'fulfilled') {
      if (result.value) loaded.push(result.value)
    } else {
      // Diagnosable without leaking the server's text into the page.
      console.error('ResultsPage: could not read one verdict.', result.reason)
    }
  }
  const [first, ...rest] = loaded
  return {
    latest: first
      ? {
          runId: first.entry.run_id,
          question: first.entry.query,
          view: first.view,
          sources: first.sources,
          corpusMissing: false,
        }
      : null,
    earlier: rest.map((row) => ({
      runId: row.entry.run_id,
      question: row.entry.query,
      stance: row.view.stance,
      share: row.view.confidence,
      date: row.entry.created_at,
    })),
  }
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
    />
  )
}
