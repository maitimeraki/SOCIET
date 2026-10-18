import { useEffect, useState } from 'react'
import { Link, NavLink, Navigate, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useRunStore } from '../run/runStore'
import { convergenceSeries, isLive, railState, rosterProgress, streamItems, verdictView } from '../run/selectors'
import { toast } from '../components/ui/Toast'
import StageRail from '../components/common/StageRail'
import WarningList from '../components/common/WarningList'
import RunHeader from '../components/run/RunHeader'
import RosterStage from '../components/run/RosterStage'
import EventStream from '../components/run/EventStream'
import ArtifactsTab from '../components/run/ArtifactsTab'
import AgentsTab from '../components/run/AgentsTab'
import ChamberFloor from '../components/chamber/ChamberFloor'
import ConvergenceTape from '../components/chamber/ConvergenceTape'
import VerdictHero from '../components/verdict/VerdictHero'
import DivisionBars from '../components/verdict/DivisionBars'
import FinalStanceTable from '../components/verdict/FinalStanceTable'
import EntityChips from '../components/verdict/EntityChips'
import GraphCanvas from '../components/graph/GraphCanvas'
import GraphPane, { mapCounts } from '../components/workspace/GraphPane'
import NodeDetailsDrawer from '../components/run/NodeDetailsDrawer'
import type { MapSummary, PaneState } from '../components/workspace/Workspace'
import { useGraphStore } from '../graph/graphStore'

/** §9.4 The pane's caption — the run view has no build step to name, so it names the map itself. */
const MAP_STEP = 'The map'

const TABS = ['roster', 'floor', 'verdict', 'agents', 'artifacts'] as const
export type RunTab = (typeof TABS)[number]
const isRunTab = (value: string | undefined): value is RunTab =>
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
  const corpusMissing = useRunStore((s) => s.corpusMissing)
  const maxRounds = run.config?.max_rounds ?? null

  // §9/D14 — the one map's text alternative and its pane geometry. The map is a sibling of every tab's
  // body (below), so switching tabs or rounds never unmounts it. Task 4.5 sets the floor beside it.
  const nodes = useGraphStore((s) => s.nodes)
  const edges = useGraphStore((s) => s.edges)
  const mapSummary: MapSummary = { counts: mapCounts(nodes, edges), busiest: [], step: MAP_STEP }
  const [paneState, setPaneState] = useState<PaneState>('split')

  useEffect(() => {
    if (runId) void loadAndConnect(runId)
  }, [runId, loadAndConnect])

  useEffect(() => () => useRunStore.getState().disconnect(), [])

  const progress = rosterProgress(run)
  const view = verdictView(run)
  const exportRun = () => {
    const doc = {
      run_id: run.runId,
      query: run.query,
      dataset_id: run.datasetId,
      status: run.status,
      config: run.config,
      rounds_executed: run.rounds.length,
      verdict: run.verdict,
      roster: run.roster,
      events,
    }
    const blob = new Blob([JSON.stringify(doc, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${run.runId ?? 'run'}_run.json`
    anchor.click()
    // Deferred: revoking synchronously after click() is racy in Firefox.
    setTimeout(() => URL.revokeObjectURL(url), 0)
    toast('success', 'Export downloaded')
  }

  const location = useLocation()
  const replayFrom = (location.state as { replayFrom?: number } | null)?.replayFrom
  const [scrubbed, setScrubbed] = useState<number | null>(null)
  const [lastReplayFrom, setLastReplayFrom] = useState<number | undefined>(undefined)
  const [lastRunId, setLastRunId] = useState(runId)

  const series = convergenceSeries(run)
  const latestRound = run.rounds.length > 0 ? run.rounds[run.rounds.length - 1].round : null

  // A different runId is a different run — the previous run's scrub position must not leak.
  if (runId !== lastRunId) {
    setLastRunId(runId)
    setLastReplayFrom(undefined)
    setScrubbed(null)
  }

  // The verdict's "Replay this run" navigates within this same route, so the component
  // never remounts — watch the arriving replay state instead of an initializer.
  // Stale or out-of-range values are ignored; valid ones clamp to the latest round.
  if (
    replayFrom != null && Number.isInteger(replayFrom) && replayFrom >= 1 &&
    replayFrom !== lastReplayFrom && latestRound !== null
  ) {
    setLastReplayFrom(replayFrom)
    setScrubbed(Math.min(replayFrom, latestRound))
  }

  const activeRound = scrubbed ?? latestRound

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
      <nav className="flex items-center gap-1 border-b border-ink-4">
        {TABS.map((name) => (
          <NavLink
            key={name}
            to={`/runs/${runId}/${name}`}
            className={({ isActive }) =>
              `px-3 py-2 text-body capitalize transition-colors ${
                isActive ? 'text-ink shadow-[inset_0_-2px_0_0_var(--color-datum)]' : 'text-ink-2 hover:text-ink'
              }`
            }
          >
            {name}
          </NavLink>
        ))}
      </nav>

      {/* §9/D14 — the one map. It is a sibling of the tabs' bodies, never inside one, so switching
          tab or round cannot unmount it; Task 4.5 pairs the floor with it in this pane, not a second. */}
      <GraphPane mapId={runId} state={paneState} onStateChange={setPaneState} summary={mapSummary}>
        <div className="relative">
          <GraphCanvas datasetId={run.datasetId ?? ''} />
          {/* The material read found nothing — said in words IN the map's own region, over a map that
              is not blank (the run's experts and opinions still stand), and never a silent empty map. */}
          {corpusMissing && (
            <div className="absolute inset-0 flex items-center justify-center bg-map-ground/90 p-6">
              <p role="status" className="max-w-sm text-center text-body text-ink-2">
                The material behind this decision is no longer available.
              </p>
            </div>
          )}
        </div>
      </GraphPane>

      {tab === 'roster' && (
        <RosterStage
          question={run.query}
          intent={run.intent}
          selection={run.selection}
          profiles={run.roster}
          progress={progress}
          onSkip={() => navigate(`/runs/${runId}/floor`)}
          floorSlot={<ChamberFloor roster={run.roster} rounds={[]} activeRound={null} livePairs={{}} />}
        />
      )}
      {tab === 'floor' && (
        <div className="grid gap-6 min-[900px]:grid-cols-[3fr_2fr]">
          <div className="space-y-4">
            <div className={`plot-ground p-4 ${run.status === 'failed' ? 'opacity-40' : ''}`}>
              <ChamberFloor
                roster={run.roster}
                rounds={run.rounds}
                activeRound={activeRound}
                livePairs={run.livePairs}
                onOpenProfile={() => navigate(`/runs/${runId}/agents`)}
              />
              <div className="mt-3 flex items-center justify-center gap-3 text-micro text-ink-3">
                <button type="button" aria-label="Previous round" disabled={activeRound === null || activeRound <= 1} onClick={() => setScrubbed(Math.max(1, (activeRound ?? 1) - 1))} className="inline-flex min-h-6 min-w-6 items-center justify-center rounded-[4px] px-2 py-0.5 hover:bg-survey-paper-2 disabled:opacity-40">◀</button>
                <span className="tnum font-measurement">{activeRound === null ? 'live' : `round ${activeRound}`}</span>
                <button type="button" aria-label="Next round" disabled={scrubbed === null} onClick={() => setScrubbed((current) => (current === null ? current : current >= (latestRound ?? 1) ? null : current + 1))} className="inline-flex min-h-6 min-w-6 items-center justify-center rounded-[4px] px-2 py-0.5 hover:bg-survey-paper-2 disabled:opacity-40">▶</button>
                <button type="button" onClick={() => setScrubbed(null)} className="rounded-[4px] px-2 py-0.5 text-datum hover:bg-survey-paper-2">End — back to live</button>
              </div>
            </div>
            <ConvergenceTape ticks={series} threshold={run.config?.convergence_threshold ?? 0.8} activeRound={activeRound} />
            {run.verdict && (
              <div className="flex items-center justify-between border-t border-ink-4 pt-3">
                <p className="text-body text-ink">
                  {run.verdict.converged ? 'Converged — the verdict is ready.' : 'Verdict ready — a plurality, not a consensus.'}
                </p>
                <Link to={`/runs/${runId}/verdict`} className="text-body text-datum hover:text-datum">
                  Open verdict →
                </Link>
              </div>
            )}
          </div>
          <div className="space-y-3">
            {run.status === 'failed' && (
              <div className="border-t border-route/40 pt-3">
                <p className="text-body text-ink">The debate stopped: {run.error ?? 'unknown error'}.</p>
                <div className="mt-2 flex items-center gap-4">
                  <a href="#run-stream" className="text-body text-datum hover:text-datum">
                    See what happened ↓
                  </a>
                  <Link to="/new/society" className="text-body text-ink-2 hover:text-ink">
                    Start a new run
                  </Link>
                </div>
              </div>
            )}
            <div id="run-stream">
              <EventStream items={streamItems(run)} live={isLive(run)} />
            </div>
          </div>
        </div>
      )}
      {tab === 'verdict' && (
        view ? (
          <div className="space-y-10">
            <VerdictHero
              stance={view.stance}
              confidence={view.confidence}
              converged={view.converged}
              summary={view.summary}
              narrative={view.narrative}
              narrativeStatus={view.narrativeStatus}
              dissentingViews={view.dissentingViews}
              evidence={view.evidence}
              onReplay={() => navigate(`/runs/${runId}/floor`, { state: { replayFrom: 1 } })}
              onExport={exportRun}
              onNew={() => navigate('/new/society')}
            />
            <section>
              <h2 className="mb-4 text-heading text-ink">The division</h2>
              <DivisionBars clusters={view.clusters} />
            </section>
            <section>
              <h2 className="mb-4 text-heading text-ink">Final stances</h2>
              <FinalStanceTable run={run} />
            </section>
            <section>
              <h2 className="mb-4 text-heading text-ink">On the record</h2>
              <EntityChips supporting={view.supporting} opposing={view.opposing} />
            </section>
            {view.warnings.length > 0 && (
              <section>
                <h2 className="mb-4 text-heading text-ink">Warnings ({view.warnings.length})</h2>
                <WarningList warnings={view.warnings} />
              </section>
            )}
          </div>
        ) : (
          <p className="text-body text-ink-3">The verdict appears when the debate completes.</p>
        )
      )}
      {tab === 'agents' && <AgentsTab run={run} />}
      {tab === 'artifacts' && <ArtifactsTab run={run} events={events} />}
      {/* §9.5 The open entry's details — a sibling of the pane, never a child of the map host (the host
          is hidden when the pane is minimised, and a dialog inside a hidden subtree is unreachable). */}
      <NodeDetailsDrawer />
    </div>
  )
}
