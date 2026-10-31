import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Navigate, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useRunStore } from '../run/runStore'
import { rosterProgress } from '../run/selectors'
import Button from '../components/ui/Button'
import SectionNav, { sectionPanelId, sectionTabId } from '../components/ui/SectionNav'
import RunHeader from '../components/run/RunHeader'
import RosterStage from '../components/run/RosterStage'
import FlowView from '../components/run/FlowView'
import ArtifactsTab from '../components/run/ArtifactsTab'
import AgentsTab from '../components/run/AgentsTab'
import ReportDocument from '../components/run/ReportDocument'
import { reportFromState } from '../components/run/reportFromState'
import ChamberFloor from '../components/chamber/ChamberFloor'
import type { RunEvent } from '../run/events'
import type { RunState } from '../run/reducer'

const TABS = ['roster', 'floor', 'verdict', 'agents', 'artifacts'] as const
export type RunTab = (typeof TABS)[number]
const isRunTab = (value: string | undefined): value is RunTab =>
  (TABS as readonly string[]).includes(value ?? '')

/** §13 — the rendered tab word; the path segment stays the internal identifier (`agents`). */
const TAB_LABELS: Record<RunTab, string> = {
  roster: 'Roster',
  floor: 'Debate',
  verdict: 'Report',
  agents: 'Experts',
  artifacts: 'Record',
}

const NAV_PREFIX = 'run'
const NAV_ITEMS = TABS.map((key) => ({ key, label: TAB_LABELS[key] }))

/**
 * §14.4 The run's one nav strip — a real tablist. The strip scrolls inside its own row at 390px
 * (§14.5), so the page never scrolls sideways.
 */
function RunNav({ runId, tab, onNavigate }: { runId: string; tab: RunTab; onNavigate: (path: string) => void }) {
  return (
    <SectionNav
      idPrefix={NAV_PREFIX}
      items={NAV_ITEMS}
      active={tab}
      onSelect={(key) => onNavigate(`/runs/${runId}/${key}`)}
      className="overflow-x-auto"
    />
  )
}

export interface RunWorkProps {
  run: RunState
  events: RunEvent[]
  tab: RunTab
  runId: string
  /** The pass being replayed; null = live. */
  scrubbed: number | null
  /** The newest pass the run has, for the scrubber's bounds; null before any pass has landed. */
  latestRound: number | null
  onScrub: (next: number | null) => void
  onNavigate: (path: string) => void
  onReplay: () => void
}

/**
 * §9.4 The run's active section — the work the activity pane holds. Shared by the live host and the
 * pure view, so the two can never drift: the only thing that differs between them is the wrapper
 * around this node (`Workspace` owns the pane state; `WorkspaceView` takes it as a prop).
 */
function RunWork({ run, events, tab, runId, scrubbed, latestRound, onScrub, onNavigate, onReplay }: RunWorkProps) {
  const progress = rosterProgress(run)
  const activeRound = scrubbed ?? latestRound

  const renderTab = (key: RunTab): ReactNode => {
    switch (key) {
      case 'roster':
        return (
          <RosterStage
            question={run.query}
            intent={run.intent}
            selection={run.selection}
            profiles={run.roster}
            progress={progress}
            onSkip={() => onNavigate(`/runs/${runId}/floor`)}
            floorSlot={<ChamberFloor roster={run.roster} rounds={[]} activeRound={null} livePairs={{}} />}
          />
        )
      case 'floor':
        return <FlowView run={run} activeRound={activeRound} latestRound={latestRound} onScrub={onScrub} onNavigate={onNavigate} />
      case 'verdict': {
        // §12.8 — the report tab renders the filed report itself: one model, derived once, the same
        // object every export serializes. The interactive affordances live beside it.
        const report = reportFromState(run)
        return report ? (
          <div className="space-y-8">
            <ReportDocument report={report} />
            <div className="flex flex-wrap items-center gap-3 print:hidden">
              <Button onClick={onReplay}>Replay this decision</Button>
              <Button variant="ghost" onClick={() => onNavigate('/new/society')}>
                Start a new decision
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-body text-ink-3">The report appears when the debate completes.</p>
        )
      }
      case 'agents':
        return <AgentsTab run={run} />
      case 'artifacts':
        return <ArtifactsTab run={run} events={events} />
    }
  }

  return (
    <>
      <div
        role="tabpanel"
        id={sectionPanelId(NAV_PREFIX, 'roster')}
        aria-labelledby={sectionTabId(NAV_PREFIX, 'roster')}
        hidden={tab !== 'roster'}
      >
        {tab === 'roster' ? renderTab('roster') : null}
      </div>
      <div
        role="tabpanel"
        id={sectionPanelId(NAV_PREFIX, 'floor')}
        aria-labelledby={sectionTabId(NAV_PREFIX, 'floor')}
        hidden={tab !== 'floor'}
      >
        {tab === 'floor' ? renderTab('floor') : null}
      </div>
      <div
        role="tabpanel"
        id={sectionPanelId(NAV_PREFIX, 'verdict')}
        aria-labelledby={sectionTabId(NAV_PREFIX, 'verdict')}
        hidden={tab !== 'verdict'}
      >
        {tab === 'verdict' ? renderTab('verdict') : null}
      </div>
      <div
        role="tabpanel"
        id={sectionPanelId(NAV_PREFIX, 'agents')}
        aria-labelledby={sectionTabId(NAV_PREFIX, 'agents')}
        hidden={tab !== 'agents'}
      >
        {tab === 'agents' ? renderTab('agents') : null}
      </div>
      <div
        role="tabpanel"
        id={sectionPanelId(NAV_PREFIX, 'artifacts')}
        aria-labelledby={sectionTabId(NAV_PREFIX, 'artifacts')}
        hidden={tab !== 'artifacts'}
      >
        {tab === 'artifacts' ? renderTab('artifacts') : null}
      </div>
    </>
  )
}

/** The verdict opens once per run, and never over itself. */
// eslint-disable-next-line react-refresh/only-export-components -- shouldAutoOpenVerdict is the tested open-once rule
export function shouldAutoOpenVerdict(hasVerdict: boolean, seen: boolean, tab: string): boolean {
  return hasVerdict && !seen && tab !== 'verdict'
}

/**
 * The pure view — the run and the tab are plain props, so the page renders to static markup
 * (Rulings F17/F23). The map pane and its host belong to `WorkspaceShell`; this is the run's work
 * region: the nav strip and the active section.
 */
export function RunPageView(runWorkProps: RunWorkProps) {
  const { runId, tab, onNavigate } = runWorkProps
  return (
    <>
      <RunNav runId={runId} tab={tab} onNavigate={onNavigate} />
      <RunWork {...runWorkProps} />
    </>
  )
}

export default function RunPage() {
  const { runId, tab } = useParams()
  const navigate = useNavigate()
  const run = useRunStore((s) => s.run)
  const events = useRunStore((s) => s.events)
  const connection = useRunStore((s) => s.connection)
  const maxRounds = run.config?.max_rounds ?? null

  const location = useLocation()
  const replayFrom = (location.state as { replayFrom?: number } | null)?.replayFrom
  const [scrubbed, setScrubbed] = useState<number | null>(null)
  const [lastReplayFrom, setLastReplayFrom] = useState<number | undefined>(undefined)
  const [lastRunId, setLastRunId] = useState(runId)

  const latestRound = run.rounds.length > 0 ? run.rounds[run.rounds.length - 1].round : null
  const progress = rosterProgress(run)

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

  // The map replays the pass the scrubber names once the run is settled. The map host and the socket
  // lifetime belong to `WorkspaceShell`, so the page only asks the store to re-seed — the guard in
  // `seedMap` makes a repeated pass a no-op (D14, §11.2). The store must already hold THIS run: on a
  // fresh handoff this page mounts before the shell's `loadAndConnect`, and seeding there would
  // rebuild the previous, completed run over the extraction map the handoff exists to preserve.
  useEffect(() => {
    if (run.runId !== runId) return
    if (run.status === 'complete' || run.status === 'failed') {
      useRunStore.getState().seedMap(scrubbed)
    }
  }, [runId, scrubbed, run.status, run.runId])

  // Handoff: auto-switch to the floor only while the user is on the roster tab (§7.5).
  useEffect(() => {
    if (runId && tab === 'roster' && progress.phase === 'seated' && run.status !== 'complete') {
      navigate(`/runs/${runId}/floor`, { replace: true })
    }
  }, [runId, tab, progress.phase, run.status, navigate])

  // Auto-open the verdict once per run. The store can still hold the previous run on mount (the
  // shell loads after child effects), so a stale verdict must not navigate this run to /verdict.
  const verdictSeen = useRef(false)
  const verdictRunId = useRef(runId)
  useEffect(() => {
    if (verdictRunId.current !== runId) {
      verdictRunId.current = runId
      verdictSeen.current = false
    }
    if (run.runId !== runId) return
    if (!shouldAutoOpenVerdict(Boolean(run.verdict), verdictSeen.current, tab ?? '')) return
    verdictSeen.current = true
    navigate(`/runs/${runId}/verdict`, { replace: true })
  }, [run.verdict, run.runId, tab, runId, navigate])

  if (!runId) return null
  if (!isRunTab(tab)) {
    const smartDefault: RunTab = run.verdict ? 'verdict' : progress.phase === 'seated' ? 'floor' : 'roster'
    return <Navigate to={`/runs/${runId}/${smartDefault}`} replace />
  }

  return (
    <div className="space-y-5">
      <RunHeader run={run} connection={connection} maxRounds={maxRounds} />
      {/* §9 The map host and the socket lifetime live in `WorkspaceShell`; the page renders the run's
          work region only, so a section change never remounts the canvas (D14). */}
      <RunPageView
        run={run}
        events={events}
        tab={tab}
        runId={runId}
        scrubbed={scrubbed}
        latestRound={latestRound}
        onScrub={setScrubbed}
        onNavigate={navigate}
        onReplay={() => navigate(`/runs/${runId}/floor`, { state: { replayFrom: 1 } })}
      />
    </div>
  )
}
