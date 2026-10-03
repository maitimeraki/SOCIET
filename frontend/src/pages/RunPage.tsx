import { useEffect } from 'react'
import { NavLink, Navigate, useNavigate, useParams } from 'react-router-dom'
import { useRunStore } from '../run/runStore'
import { isLive, railState, rosterProgress, streamItems } from '../run/selectors'
import { useDraftStore } from '../wizard/draftStore'
import StageRail from '../components/common/StageRail'
import RunHeader from '../components/run/RunHeader'
import RosterStage from '../components/run/RosterStage'
import EventStream from '../components/run/EventStream'
import ArtifactsTab from '../components/run/ArtifactsTab'

const TABS = ['roster', 'floor', 'verdict', 'agents', 'artifacts'] as const
export type RunTab = (typeof TABS)[number]
export const isRunTab = (value: string | undefined): value is RunTab =>
  (TABS as readonly string[]).includes(value ?? '')

const RAIL_TARGETS: Record<string, RunTab> = {
  ingest: 'artifacts',
  graph: 'artifacts',
  question: 'artifacts',
  roster: 'roster',
  debate: 'floor',
  verdict: 'verdict',
}

export default function RunPage() {
  const { runId, tab } = useParams()
  const navigate = useNavigate()
  const run = useRunStore((s) => s.run)
  const events = useRunStore((s) => s.events)
  const connection = useRunStore((s) => s.connection)
  const loadAndConnect = useRunStore((s) => s.loadAndConnect)
  const maxRounds = useDraftStore((s) => s.graphSummary) ? null : null // config max_rounds rides the run doc (Task 20); null until then

  useEffect(() => {
    if (runId) void loadAndConnect(runId)
  }, [runId, loadAndConnect])

  useEffect(() => () => useRunStore.getState().disconnect(), [])

  const progress = rosterProgress(run)

  // Handoff: auto-switch to the floor only while the user is on the roster tab (§7.5).
  useEffect(() => {
    if (runId && tab === 'roster' && progress.phase === 'seated' && run.status !== 'complete') {
      navigate(`/runs/${runId}/floor`, { replace: true })
    }
  }, [runId, tab, progress.phase, run.status, navigate])

  if (!runId) return null
  if (!isRunTab(tab)) {
    const smartDefault: RunTab = run.verdict ? 'verdict' : progress.phase === 'seated' ? 'floor' : 'roster'
    return <Navigate to={`/runs/${runId}/${smartDefault}`} replace />
  }

  return (
    <div className="space-y-5">
      <RunHeader run={run} connection={connection} maxRounds={maxRounds} />
      <StageRail
        stages={railState(run)}
        activeKey={tab}
        onSelect={(key) => navigate(`/runs/${runId}/${RAIL_TARGETS[key] ?? 'roster'}`)}
      />
      <nav className="flex items-center gap-1 border-b border-ink-700">
        {TABS.map((name) => (
          <NavLink
            key={name}
            to={`/runs/${runId}/${name}`}
            className={({ isActive }) =>
              `px-3 py-2 text-body capitalize transition-colors ${
                isActive ? 'text-paper shadow-[inset_0_-2px_0_0_var(--color-accent)]' : 'text-paper-dim hover:text-paper'
              }`
            }
          >
            {name}
          </NavLink>
        ))}
      </nav>

      {tab === 'roster' && (
        <RosterStage
          question={run.query}
          intent={run.intent}
          selection={run.selection}
          profiles={run.roster}
          progress={progress}
          onSkip={() => navigate(`/runs/${runId}/floor`)}
        />
      )}
      {tab === 'floor' && (
        <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
          <div className="rounded-[6px] border border-ink-700 bg-ink-900 p-4 text-body text-paper-mute">
            The floor arrives in Task 16 — {run.roster.length} seated so far.
          </div>
          <EventStream items={streamItems(run)} live={isLive(run)} />
        </div>
      )}
      {tab === 'verdict' && (
        <p className="text-body text-paper-mute">
          {run.verdict ? run.verdict.summary : 'The verdict appears when the debate completes.'}
        </p>
      )}
      {tab === 'agents' && (
        <p className="text-body text-paper-mute">
          {run.roster.length} agents seated{run.activations.length > 0 ? ` · ${run.activations.length} activations` : ''}
        </p>
      )}
      {tab === 'artifacts' && <ArtifactsTab run={run} events={events} />}
    </div>
  )
}
