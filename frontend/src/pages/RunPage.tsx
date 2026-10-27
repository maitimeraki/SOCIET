import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, Navigate, useLocation, useNavigate, useParams } from 'react-router-dom'
import { CaretLeft, CaretRight } from '@phosphor-icons/react'
import { useRunStore } from '../run/runStore'
import { convergenceSeries, isLive, rosterProgress, streamItems, verdictView } from '../run/selectors'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import { ruleClasses } from '../components/ui/Rule'
import SectionNav, { sectionPanelId, sectionTabId } from '../components/ui/SectionNav'
import RunHeader from '../components/run/RunHeader'
import RosterStage from '../components/run/RosterStage'
import EventStream from '../components/run/EventStream'
import ArtifactsTab from '../components/run/ArtifactsTab'
import AgentsTab from '../components/run/AgentsTab'
import AnswerDocument, { sourceTitles } from '../components/run/AnswerDocument'
import ChamberFloor from '../components/chamber/ChamberFloor'
import ConvergenceTape from '../components/chamber/ConvergenceTape'
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
  verdict: 'Verdict',
  agents: 'Experts',
  artifacts: 'Artifacts',
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
  /** The run's material is gone — the answer states it rather than omitting the sources (§8.5). */
  corpusMissing?: boolean
  onScrub: (next: number | null) => void
  onNavigate: (path: string) => void
  onReplay: () => void
}

/**
 * §9.4 The run's active section — the work the activity pane holds. Shared by the live host and the
 * pure view, so the two can never drift: the only thing that differs between them is the wrapper
 * around this node (`Workspace` owns the pane state; `WorkspaceView` takes it as a prop).
 */
function RunWork({ run, events, tab, runId, scrubbed, latestRound, corpusMissing, onScrub, onNavigate, onReplay }: RunWorkProps) {
  const progress = rosterProgress(run)
  const view = verdictView(run)
  const series = convergenceSeries(run)
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
        return (
          <div className="grid gap-6 min-[900px]:grid-cols-[3fr_2fr]">
            <div className="space-y-4">
              {/* The floor is the one card; every record inside it is ruled, never boxed. */}
              <Card className={run.status === 'failed' ? 'opacity-40' : ''}>
                <ChamberFloor
                  roster={run.roster}
                  rounds={run.rounds}
                  activeRound={activeRound}
                  livePairs={run.livePairs}
                  onOpenProfile={() => onNavigate(`/runs/${runId}/agents`)}
                />
                <div className="mt-3 flex flex-wrap items-center justify-center gap-3 text-micro text-ink-3">
                  <button type="button" aria-label="Previous pass" disabled={activeRound === null || activeRound <= 1} onClick={() => onScrub(Math.max(1, (activeRound ?? 1) - 1))} className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-xs px-2 py-0.5 hover:bg-ground-2 disabled:opacity-40"><CaretLeft size={14} aria-hidden="true" /></button>
                  <span className="tnum font-measurement">{activeRound === null ? 'live' : `pass ${activeRound}`}</span>
                  <button type="button" aria-label="Next pass" disabled={scrubbed === null} onClick={() => onScrub(scrubbed === null ? null : scrubbed >= (latestRound ?? 1) ? null : scrubbed + 1)} className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-xs px-2 py-0.5 hover:bg-ground-2 disabled:opacity-40"><CaretRight size={14} aria-hidden="true" /></button>
                  <button type="button" onClick={() => onScrub(null)} className="inline-flex min-h-11 items-center rounded-xs px-2 py-0.5 text-accent hover:bg-ground-2">End — back to live</button>
                </div>
              </Card>
              <ConvergenceTape ticks={series} threshold={run.config?.convergence_threshold ?? 0.8} activeRound={activeRound} />
              {run.verdict && (
                <div className={`${ruleClasses('top')} flex flex-wrap items-center justify-between gap-2 pt-3`}>
                  <p className="text-body text-ink">
                    {run.verdict.converged ? 'Converged — the verdict is ready.' : 'Verdict ready — a plurality, not a consensus.'}
                  </p>
                  <Link to={`/runs/${runId}/verdict`} className="inline-flex min-h-11 items-center text-body text-accent hover:text-accent">
                    Open verdict →
                  </Link>
                </div>
              )}
            </div>
            <div className="space-y-3">
              {run.status === 'failed' && (
                <div className={`${ruleClasses('top')} pt-3`}>
                  <p className="text-body text-ink">The debate stopped: {run.error ?? 'unknown error'}.</p>
                  <div className="mt-2 flex flex-wrap items-center gap-4">
                    <a href="#run-stream" className="inline-flex min-h-11 items-center text-body text-accent hover:text-accent">
                      See what happened ↓
                    </a>
                    <Link to="/new/society" className="inline-flex min-h-11 items-center text-body text-ink-2 hover:text-ink">
                      Start a new decision
                    </Link>
                  </div>
                </div>
              )}
              <div id="run-stream">
                <EventStream items={streamItems(run)} live={isLive(run)} />
              </div>
            </div>
          </div>
        )
      case 'verdict':
        return view ? (
          <div className="space-y-8">
            {/* §8.5 — the answer IS the reading view and the export: one document, derived once. The
                raw-JSON dump it replaces is retired; the export lives inside the document, so what is
                read here and what leaves are the same. The interactive affordances live beside it. */}
            <AnswerDocument
              runId={runId}
              question={run.query}
              view={view}
              sources={sourceTitles(run.roster)}
              corpusMissing={corpusMissing ?? false}
            />
            <div className="flex flex-wrap items-center gap-3 print:hidden">
              <Button onClick={onReplay}>Replay this decision</Button>
              <Button variant="ghost" onClick={() => onNavigate('/new/society')}>
                Start a new decision
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-body text-ink-3">The verdict appears when the debate completes.</p>
        )
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
  const corpusMissing = useRunStore((s) => s.corpusMissing)
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
  // `seedMap` makes a repeated pass a no-op (D14, §11.2).
  useEffect(() => {
    if (run.status === 'complete' || run.status === 'failed') {
      useRunStore.getState().seedMap(scrubbed)
    }
  }, [scrubbed, run.status])

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
      {/* §9 The map host and the socket lifetime live in `WorkspaceShell`; the page renders the run's
          work region only, so a section change never remounts the canvas (D14). */}
      <RunPageView
        run={run}
        events={events}
        tab={tab}
        runId={runId}
        scrubbed={scrubbed}
        latestRound={latestRound}
        corpusMissing={corpusMissing}
        onScrub={setScrubbed}
        onNavigate={navigate}
        onReplay={() => navigate(`/runs/${runId}/floor`, { state: { replayFrom: 1 } })}
      />
    </div>
  )
}
