import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, getRun, getRunGraph } from '../api/rest'
import { fold } from '../run/reducer'
import { verdictView } from '../run/selectors'
import type { VerdictView } from '../run/selectors'
import AnswerDocument, { sourceTitles } from '../components/run/AnswerDocument'
import { buttonClasses } from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import ErrorState from '../components/ui/ErrorState'
import Skeleton from '../components/ui/Skeleton'
import { DASHBOARD_COPY } from '../pages/dashboardCopy'
import { sharedDecisionSubject } from '../pages/dashboardSubject'

/** What the section hands the view: the newest answered decision's answer, or nothing yet. */
interface AnswerSlice {
  runId: string
  question: string
  view: VerdictView
  sources: string[]
  corpusMissing: boolean
}

/** The subject walk's outcome: the answer when one exists, and the newest decision either way. */
interface LoadedAnswer {
  slice: AnswerSlice | null
  pendingRunId: string | null
}

export interface ResultsViewProps {
  runId: string | null
  question: string
  view: VerdictView | null
  sources: string[]
  corpusMissing: boolean
  /** The newest decision, when it has not filed an answer — the section names it and links to it. */
  pendingRunId: string | null
  loading: boolean
  failed: boolean
  /** The server's own failure message, when there is one; the standing copy stands in otherwise. */
  failDetail?: string
  onRetry: () => void
}

/**
 * The last answer (§14.3) — the newest decision that has filed one, rendered as the filed sheet
 * (through `AnswerDocument`, the same document the run page reads and exports). With no answer
 * yet, the section says so plainly and links the decision that owes one, rather than showing an
 * older answer as if it were the newest.
 */
export function ResultsView({
  runId,
  question,
  view,
  sources,
  corpusMissing,
  pendingRunId,
  loading,
  failed,
  failDetail,
  onRetry,
}: ResultsViewProps) {
  return (
    <div className="mt-6">
      {failed ? (
        // A failure is never an empty answer: it is surfaced, with a retry.
        <ErrorState
          title={DASHBOARD_COPY.error.title}
          detail={failDetail || DASHBOARD_COPY.error.lastAnswer}
          onRetry={onRetry}
          retryLabel={DASHBOARD_COPY.actions.retry}
        />
      ) : loading ? (
        <Skeleton className="h-64 w-full" />
      ) : view && runId ? (
        <AnswerDocument runId={runId} question={question} view={view} sources={sources} corpusMissing={corpusMissing} />
      ) : pendingRunId ? (
        <EmptyState
          line={DASHBOARD_COPY.empty.notAnswered}
          action={
            <Link to={`/runs/${pendingRunId}`} className={buttonClasses('secondary', 40, 'min-h-11')}>
              {DASHBOARD_COPY.actions.openDecision}
            </Link>
          }
        />
      ) : (
        <EmptyState
          line={DASHBOARD_COPY.empty.lastAnswer}
          action={
            <Link to="/new" className={buttonClasses('primary', 40, 'min-h-11')}>
              {DASHBOARD_COPY.startFree}
            </Link>
          }
        />
      )}
    </div>
  )
}

/**
 * The section's container. The subject is the newest decision that has filed an answer, found by
 * the shared keyset walk (`dashboardSubject`) — the same subject "Your panel" describes — and then
 * read by id with `getRun`. Its stored events are folded the same way the live store folds them,
 * and its material is read on its own to know whether the sources still stand. A retry either
 * bumps the page's refresh key (one refresh for the whole surface) or, standalone, this section's
 * own attempt.
 */
export interface ResultsSectionProps {
  /** Bumped by the dashboard when any section's retry asks the page to refresh. */
  refreshKey?: number
  /** The page's refresh; when absent the section retries on its own. */
  onRefresh?: () => void
  /** The dashboard visit's shared-walk epoch, so this section and Your panel read one subject. */
  subjectEpoch?: number
}

export default function ResultsSection({
  refreshKey = 0,
  onRefresh,
  subjectEpoch,
}: ResultsSectionProps = {}) {
  const [answer, setAnswer] = useState<AnswerSlice | null>(null)
  const [pendingRunId, setPendingRunId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [failDetail, setFailDetail] = useState<string>()
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    const load = async (): Promise<LoadedAnswer> => {
      const subject = await sharedDecisionSubject(subjectEpoch)
      const target = subject.answered
      if (!target) return { slice: null, pendingRunId: subject.newest?.run_id ?? null }
      const doc = await getRun(target.run_id)
      const folded = fold(doc.events)
      const view = verdictView(folded)
      if (!view) return { slice: null, pendingRunId: target.run_id }
      let corpusMissing = false
      try {
        await getRunGraph(target.run_id)
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          // The typed 404 is the only "material is gone" answer (rest.ts: no_corpus / corpus_gone).
          corpusMissing = true
        } else {
          // A transient failure is an unknown, not a missing corpus — record it, claim nothing.
          console.error('ResultsSection: could not read the material behind the last answer.', error)
        }
      }
      return {
        slice: {
          runId: target.run_id,
          question: target.query,
          view,
          sources: sourceTitles(folded.roster),
          corpusMissing,
        },
        pendingRunId: null,
      }
    }
    load()
      .then((loaded) => {
        if (cancelled) return
        setAnswer(loaded.slice)
        setPendingRunId(loaded.pendingRunId)
        setFailed(false)
        setFailDetail(undefined)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setFailed(true)
        setFailDetail(error instanceof Error ? error.message : undefined)
        setAnswer(null)
        setPendingRunId(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [attempt, refreshKey, subjectEpoch])

  const retry = () => {
    setLoading(true)
    setFailed(false)
    setFailDetail(undefined)
    if (onRefresh) onRefresh()
    else setAttempt((n) => n + 1)
  }

  return (
    <ResultsView
      runId={answer?.runId ?? null}
      question={answer?.question ?? ''}
      view={answer?.view ?? null}
      sources={answer?.sources ?? []}
      corpusMissing={answer?.corpusMissing ?? false}
      pendingRunId={pendingRunId}
      loading={loading}
      failed={failed}
      failDetail={failDetail}
      onRetry={retry}
    />
  )
}
