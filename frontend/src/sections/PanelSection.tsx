import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getRun } from '../api/rest'
import type { AgentProfile } from '../run/events'
import { sourceTitles } from '../components/run/AnswerDocument'
import { buttonClasses } from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import ErrorState from '../components/ui/ErrorState'
import PositionMark from '../components/ui/PositionMark'
import { ruleClasses } from '../components/ui/Rule'
import RuledBlock from '../components/ui/RuledBlock'
import Skeleton from '../components/ui/Skeleton'
import { DASHBOARD_COPY } from '../pages/dashboardCopy'
import { sharedDecisionSubject } from '../pages/dashboardSubject'

/**
 * Your panel (§14.3) — the experts a decision is argued by. Experts exist only inside a decision
 * (each seated per decision, keyed by its corpus and name), so the honesty notice leads and says
 * what the section cannot yet show; the experts of the newest answered decision — the same subject
 * "The last answer" describes — render below it. The heading lives on the dashboard, so this
 * renders its content only.
 */

/** The documents one expert argued from — the distinct titles off its own source links (D7). */
function ExpertSources({ profile }: { profile: AgentProfile }) {
  const titles = sourceTitles([profile])
  return (
    <span className="mt-2 block text-body text-ink-3">
      {titles.length === 0 ? 'No documents recorded for this expert.' : `Arguing from: ${titles.join(' · ')}`}
    </span>
  )
}

export interface PanelViewProps {
  /** The experts of the newest answered decision, in the order the payload seated them. */
  experts: AgentProfile[]
  /** The newest decision, when it has not filed an answer — named and linked, never guessed at. */
  pendingRunId: string | null
  loading: boolean
  failed: boolean
  /** The server's own failure message, when there is one; the standing copy stands in otherwise. */
  failDetail?: string
  onRetry: () => void
}

export function PanelView({ experts, pendingRunId, loading, failed, failDetail, onRetry }: PanelViewProps) {
  return (
    <div className="mt-6 space-y-6">
      <RuledBlock>
        Your panel is convened fresh for each decision, from your own documents. This section shows the panel of
        your most recent decision — every expert who argued it, the position each took, and the documents each
        argued from. What it cannot yet show: a panel that persists across decisions. The same expert does not
        carry over from one decision to the next, and no history of how any one of them has argued over time is
        kept.
      </RuledBlock>
      {failed ? (
        // A failure is never an empty panel: it is surfaced, with a retry.
        <ErrorState
          title={DASHBOARD_COPY.error.title}
          detail={failDetail || DASHBOARD_COPY.error.panel}
          onRetry={onRetry}
          retryLabel={DASHBOARD_COPY.actions.retry}
        />
      ) : loading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : experts.length === 0 ? (
        pendingRunId ? (
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
            line={DASHBOARD_COPY.empty.panel}
            action={
              <Link to="/new" className={buttonClasses('primary', 40, 'min-h-11')}>
                {DASHBOARD_COPY.startFree}
              </Link>
            }
          />
        )
      ) : (
        <>
          <h3 id="panel-experts" className="text-heading text-ink">
            Who argued it
          </h3>
          <ul
            aria-labelledby="panel-experts"
            className={`${ruleClasses('around')} ${ruleClasses('both')}`}
          >
            {experts.map((expert) => (
              <li key={expert.agent_id} className="py-4">
                <span className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                  <span className="text-body text-ink">{expert.identity.name}</span>
                  <PositionMark position={expert.stance} size="sm" ground="light" />
                </span>
                <span className="mt-2 block text-body text-ink-2">{expert.bio}</span>
                <ExpertSources profile={expert} />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

export interface PanelSectionProps {
  /** Bumped by the dashboard when any section's retry asks the page to refresh. */
  refreshKey?: number
  /** The page's refresh; when absent the section retries on its own. */
  onRefresh?: () => void
  /** The dashboard visit's shared-walk epoch, so this section and The last answer read one subject. */
  subjectEpoch?: number
}

/**
 * The section's container: the experts of the newest answered decision — the same subject "The
 * last answer" describes, read from the one shared walk — then that decision's stored events. A
 * retry either bumps the page's refresh key (one refresh for the whole surface) or, standalone,
 * this section's own attempt.
 */
export default function PanelSection({
  refreshKey = 0,
  onRefresh,
  subjectEpoch,
}: PanelSectionProps = {}) {
  const [experts, setExperts] = useState<AgentProfile[]>([])
  const [pendingRunId, setPendingRunId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [failDetail, setFailDetail] = useState<string>()
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    const load = async (): Promise<{ profiles: AgentProfile[]; pendingRunId: string | null }> => {
      const subject = await sharedDecisionSubject(subjectEpoch)
      const target = subject.answered
      if (!target) return { profiles: [], pendingRunId: subject.newest?.run_id ?? null }
      const doc = await getRun(target.run_id)
      return {
        profiles: doc.events.flatMap((event) => (event.type === 'agent' ? [event.profile] : [])),
        pendingRunId: null,
      }
    }
    load()
      .then((loaded) => {
        if (cancelled) return
        setExperts(loaded.profiles)
        setPendingRunId(loaded.pendingRunId)
        setFailed(false)
        setFailDetail(undefined)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setFailed(true)
        setFailDetail(error instanceof Error ? error.message : undefined)
        setExperts([])
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
    <PanelView
      experts={experts}
      pendingRunId={pendingRunId}
      loading={loading}
      failed={failed}
      failDetail={failDetail}
      onRetry={retry}
    />
  )
}
