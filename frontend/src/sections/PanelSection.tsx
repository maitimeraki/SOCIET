import { useEffect, useState } from 'react'
import { getRun, listRuns } from '../api/rest'
import type { AgentProfile } from '../run/events'
import { sourceTitles } from '../components/run/AnswerDocument'
import StanceChip from '../components/common/StanceChip'
import Button from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import ErrorState from '../components/ui/ErrorState'
import RuledBlock from '../components/ui/RuledBlock'
import Skeleton from '../components/ui/Skeleton'

/**
 * §8.6 Panel — the experts a decision is argued by. Experts exist only inside a decision (each seated
 * per decision, keyed by its corpus and name), so the honesty notice leads and says what the section
 * cannot yet show; the experts of the most recent decision — their positions and their documents —
 * render below it. Presentational: the data and the retry arrive as props (the default export owns the
 * fetch), so this renders under `react-dom/server` in the node-only suite where `useEffect` never fires.
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
  /** The experts of the most recent decision, in the order the payload seated them. */
  experts: AgentProfile[]
  loading: boolean
  failed: boolean
  /** The server's own failure message, when there is one; the standing copy stands in otherwise. */
  failDetail?: string
  onRetry: () => void
}

export function PanelView({ experts, loading, failed, failDetail, onRetry }: PanelViewProps) {
  return (
    <div className="space-y-6">
      <h1 className="font-titling text-display text-ink">Panel</h1>
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
          title="Couldn't reach the server"
          detail={failDetail || 'Your panel loads when the server is back.'}
          actions={
            <Button type="button" variant="secondary" onClick={onRetry}>
              Try again
            </Button>
          }
        />
      ) : loading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : experts.length === 0 ? (
        <EmptyState line="No panel yet. Start a decision and your panel is convened from your own documents." />
      ) : (
        <>
          <h2 id="panel-experts" className="text-heading text-ink">
            Who argued it
          </h2>
          <ul aria-labelledby="panel-experts" className="divide-y divide-ink-3 border-y border-ink-3">
            {experts.map((expert) => (
              <li key={expert.agent_id} className="py-4">
                <span className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                  <span className="text-body text-ink">{expert.identity.name}</span>
                  <StanceChip stance={expert.stance} size="sm" />
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

/**
 * The section's container: it owns the fetch and the retry counter the view never sees. The experts of
 * the newest decision are read the way the experts list reads them — the keyset list (newest first),
 * then that decision's stored events. Bumping `attempt` re-runs the effect — the retry affordance
 * without a second code path.
 */
export default function PanelSection() {
  const [experts, setExperts] = useState<AgentProfile[]>([])
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [failDetail, setFailDetail] = useState<string>()
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    const load = async (): Promise<AgentProfile[]> => {
      const newest = (await listRuns())[0]
      if (!newest) return []
      const doc = await getRun(newest.run_id)
      return doc.events.flatMap((event) => (event.type === 'agent' ? [event.profile] : []))
    }
    load()
      .then((profiles) => {
        if (cancelled) return
        setExperts(profiles)
        setFailed(false)
        setFailDetail(undefined)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setFailed(true)
        setFailDetail(error instanceof Error ? error.message : undefined)
        setExperts([])
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

  return <PanelView experts={experts} loading={loading} failed={failed} failDetail={failDetail} onRetry={retry} />
}
