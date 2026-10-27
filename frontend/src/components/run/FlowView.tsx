import { Link } from 'react-router-dom'
import { CaretLeft, CaretRight } from '@phosphor-icons/react'
import { convergenceSeries, isLive, streamItems } from '../../run/selectors'
import Card from '../ui/Card'
import { ruleClasses } from '../ui/Rule'
import ChamberFloor from '../chamber/ChamberFloor'
import ConvergenceTape from '../chamber/ConvergenceTape'
import EventStream from './EventStream'
import type { RunState } from '../../run/reducer'

export interface FlowViewProps {
  run: RunState
  activeRound: number | null
  latestRound: number | null
  onScrub: (next: number | null) => void
  onNavigate: (path: string) => void
}

/** §9.4 — the Debate section: the floor, the pass scrubber, the tape, and the live record. */
export default function FlowView({ run, activeRound, latestRound, onScrub, onNavigate }: FlowViewProps) {
  const series = convergenceSeries(run)
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
            onOpenProfile={() => onNavigate(`/runs/${run.runId}/agents`)}
          />
          <div className="mt-3 flex flex-wrap items-center justify-center gap-3 text-micro text-ink-3">
            <button type="button" aria-label="Previous pass" disabled={activeRound === null || activeRound <= 1} onClick={() => onScrub(Math.max(1, (activeRound ?? 1) - 1))} className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-xs px-2 py-0.5 hover:bg-ground-2 disabled:opacity-40"><CaretLeft size={14} aria-hidden="true" /></button>
            <span className="tnum font-measurement">{activeRound === null ? 'live' : `pass ${activeRound}`}</span>
            <button type="button" aria-label="Next pass" disabled={activeRound === null || activeRound >= (latestRound ?? activeRound)} onClick={() => onScrub(activeRound === null || activeRound >= (latestRound ?? activeRound) ? null : activeRound + 1)} className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-xs px-2 py-0.5 hover:bg-ground-2 disabled:opacity-40"><CaretRight size={14} aria-hidden="true" /></button>
            <button type="button" onClick={() => onScrub(null)} className="inline-flex min-h-11 items-center rounded-xs px-2 py-0.5 text-accent hover:bg-ground-2">End — back to live</button>
          </div>
        </Card>
        <ConvergenceTape ticks={series} threshold={run.config?.convergence_threshold ?? 0.8} activeRound={activeRound} />
        {run.verdict && (
          <div className={`${ruleClasses('top')} flex flex-wrap items-center justify-between gap-2 pt-3`}>
            <p className="text-body text-ink">
              {run.verdict.converged ? 'Converged — the verdict is ready.' : 'Verdict ready — a plurality, not a consensus.'}
            </p>
            <Link to={`/runs/${run.runId}/verdict`} className="inline-flex min-h-11 items-center text-body text-accent hover:text-accent">
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
}
