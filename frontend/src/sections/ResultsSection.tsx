import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, getRun, getRunGraph, listRuns } from '../api/rest'
import { fold } from '../run/reducer'
import { verdictView } from '../run/selectors'
import type { VerdictView } from '../run/selectors'
import AnswerDocument, { sourceTitles } from '../components/run/AnswerDocument'
import StanceChip from '../components/common/StanceChip'
import Button, { buttonClasses } from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import ErrorState from '../components/ui/ErrorState'
import Skeleton from '../components/ui/Skeleton'
import { fmtDate, fmtScore } from '../utils/format'

/** What the section hands the view: the newest completed decision's answer, or nothing yet. */
interface AnswerSlice {
  runId: string
  question: string
  /** The decision's own date, read off the payload — never derived from the rendered events. */
  createdAt: string
  view: VerdictView
  sources: string[]
  corpusMissing: boolean
}

export interface ResultsViewProps {
  runId: string | null
  question: string
  createdAt: string
  view: VerdictView | null
  sources: string[]
  corpusMissing: boolean
  loading: boolean
  failed: boolean
  /** The server's own failure message, when there is one; the standing copy stands in otherwise. */
  failDetail?: string
  onRetry: () => void
}

/**
 * §8.5 Verdicts — the outcome of a decision, readable and exportable. The most recent completed
 * decision's answer renders here; with none, the section says so honestly rather than showing an
 * empty document. Presentational: the data and the retry arrive as props (the default export owns the
 * fetch), so this renders under `react-dom/server` in the node-only suite where `useEffect` never fires.
 */
export function ResultsView({ runId, question, createdAt, view, sources, corpusMissing, loading, failed, failDetail, onRetry }: ResultsViewProps) {
  return (
    <div className="space-y-6">
      <h1 className="font-titling text-display text-ink">Verdicts</h1>
      {failed ? (
        // A failure is never an empty answer: it is surfaced, with a retry.
        <ErrorState
          title="Couldn't reach the server"
          detail={failDetail || 'Your verdicts load when the server is back.'}
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
      ) : view && runId ? (
        <div className="space-y-6">
          {/* §8.5/§4 the verdict opens with what it concluded: the stance as shape + word, the
              confidence as the reading's numeral, and the decision's own date. */}
          <header className="flex flex-wrap items-end justify-between gap-4 border-b border-ink-4 pb-4">
            <div className="space-y-2">
              <p className="text-label uppercase text-ink-3">The outcome</p>
              <StanceChip stance={view.stance} />
            </div>
            <div>
              <p className="tnum font-measurement text-numeral text-ink">
                {view.confidence === null ? '—' : fmtScore(view.confidence)}
              </p>
              <p className="text-label uppercase text-ink-3">Weighted confidence</p>
            </div>
            <p className="tnum font-measurement text-mono text-ink-3">
              Decided <time dateTime={createdAt}>{fmtDate(createdAt)}</time>
            </p>
          </header>
          <AnswerDocument runId={runId} question={question} view={view} sources={sources} corpusMissing={corpusMissing} />
        </div>
      ) : (
        <EmptyState
          line="The outcome of each decision — its stance, its confidence, and the strongest case against it. A verdict appears here when a decision finishes."
          action={
            <Link to="/new" className={buttonClasses('primary', 40)}>
              Start a decision
            </Link>
          }
        />
      )}
    </div>
  )
}

/**
 * The section's container: it owns the fetch and the retry counter the view never sees. The newest
 * completed decision is read from the keyset list (newest first), its stored events folded the same
 * way the live store folds them, and its material read on its own to know whether the sources still
 * stand. Bumping `attempt` re-runs the effect — the retry affordance without a second code path.
 */
export default function ResultsSection() {
  const [answer, setAnswer] = useState<AnswerSlice | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [failDetail, setFailDetail] = useState<string>()
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    const load = async (): Promise<AnswerSlice | null> => {
      const newest = (await listRuns()).find((run) => run.status === 'complete')
      if (!newest) return null
      const doc = await getRun(newest.run_id)
      const folded = fold(doc.events)
      const view = verdictView(folded)
      if (!view) return null
      let corpusMissing = false
      try {
        await getRunGraph(newest.run_id)
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          // The typed 404 is the only "material is gone" answer (rest.ts: no_corpus / corpus_gone).
          corpusMissing = true
        } else {
          // A transient failure is an unknown, not a missing corpus — record it, claim nothing.
          console.error('ResultsSection: could not read the material behind the newest decision.', error)
        }
      }
      return {
        runId: newest.run_id,
        question: newest.query,
        createdAt: newest.created_at,
        view,
        sources: sourceTitles(folded.roster),
        corpusMissing,
      }
    }
    load()
      .then((slice) => {
        if (cancelled) return
        setAnswer(slice)
        setFailed(false)
        setFailDetail(undefined)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setFailed(true)
        setFailDetail(error instanceof Error ? error.message : undefined)
        setAnswer(null)
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

  return (
    <ResultsView
      runId={answer?.runId ?? null}
      question={answer?.question ?? ''}
      createdAt={answer?.createdAt ?? ''}
      view={answer?.view ?? null}
      sources={answer?.sources ?? []}
      corpusMissing={answer?.corpusMissing ?? false}
      loading={loading}
      failed={failed}
      failDetail={failDetail}
      onRetry={retry}
    />
  )
}
