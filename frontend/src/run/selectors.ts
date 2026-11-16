import type { AgentView, ReportSources, ReportStatus, Stance, TurnInfo } from './events'
import type { RunState } from './reducer'

/** The display order of the stances (legend, tape segments, grouped lists). */
export const STANCE_ORDER: Stance[] = ['POSITIVE', 'NEUTRAL', 'ABSTAIN', 'NEGATIVE']


// ---------------------------------------------------------------------------
// Roster (profile creation) — the ①→④ sequence state
// ---------------------------------------------------------------------------

export type RosterPhase = 'reading' | 'building' | 'seated' | 'empty'

export interface RosterProgress {
  phase: RosterPhase
  built: number
  total: number | null
}

export function rosterProgress(state: RunState): RosterProgress {
  const seated = state.stages.some((stage) => stage.stage === 'round')
  const finished = state.status === 'complete' || state.stages.some((stage) => stage.stage === 'verdict')
  const built = state.roster.length
  const synthesis = state.stages.find((stage) => stage.stage === 'synthesis')
  const total =
    synthesis && typeof synthesis.fields.agents === 'number'
      ? (synthesis.fields.agents as number)
      : state.rosterTotal !== null
        ? state.rosterTotal
        : built > 0
          ? built
          : null

  if (finished && built === 0) return { phase: 'empty', built, total: 0 }
  if (seated) return { phase: 'seated', built, total }
  if (built > 0) return { phase: 'building', built, total }
  return { phase: 'reading', built, total }
}

// ---------------------------------------------------------------------------
// Rail — Ingest · Graph · Question · Roster · Debate · Verdict (§7.6)
// ---------------------------------------------------------------------------

export interface RailEntry {
  key: 'ingest' | 'graph' | 'question' | 'roster' | 'debate' | 'verdict'
  label: string
  state: 'pending' | 'running' | 'done' | 'failed'
  note?: string
}

export function railState(state: RunState): RailEntry[] {
  const seated = state.stages.some((stage) => stage.stage === 'round')
  const running = state.status === 'running'
  return [
    // A run cannot exist without ingest/graph/question — done by construction (§7.6).
    { key: 'ingest', label: 'Ingest', state: 'done', note: state.datasetId ?? undefined },
    { key: 'graph', label: 'The map', state: 'done' },
    { key: 'question', label: 'Question', state: 'done' },
    { key: 'roster', label: 'Roster', state: seated ? 'done' : running ? 'running' : 'pending' },
    {
      key: 'debate',
      label: 'Debate',
      state: !seated ? 'pending' : state.status === 'complete' ? 'done' : running ? 'running' : 'pending',
    },
    { key: 'verdict', label: 'Verdict', state: state.verdict ? 'done' : state.status === 'failed' ? 'failed' : 'pending' },
  ]
}

// ---------------------------------------------------------------------------
// Round / tape / roster maps
// ---------------------------------------------------------------------------

export function currentRound(state: RunState): number {
  return state.rounds.length > 0 ? state.rounds[state.rounds.length - 1].round : 0
}

export interface TapeTick {
  round: number
  /** Null when the pass carries no consensus (no position in its window): no shares are shown. */
  weights: Record<Stance, number> | null
  dominant: { stance: string; weightShare: number } | null
}

export function convergenceSeries(state: RunState): TapeTick[] {
  return state.rounds.map((round) => ({
    round: round.round,
    weights: round.consensus?.weights ?? null,
    dominant: round.consensus ? { stance: round.consensus.stance, weightShare: round.consensus.weight_share } : null,
  }))
}

export function rosterById(state: RunState): Map<string, AgentView> {
  return new Map(state.roster.map((profile) => [profile.name, profile]))
}

export const isLive = (state: RunState): boolean => state.status === 'queued' || state.status === 'running'

// ---------------------------------------------------------------------------
// The Record — the live stream (§9.1)
// ---------------------------------------------------------------------------

export type StreamItem =
  | { kind: 'round-header'; round: number; pairs: number; at: number }
  | { kind: 'turn'; round: number; turn: TurnInfo }
  | { kind: 'pending'; pairId: string; a: string; b: string }
  | { kind: 'commit'; round: number; opinions: number; edges: number; failed: boolean }
  | { kind: 'activation'; round: number; agents: string[]; reasons: Record<string, string> }
  | { kind: 'warning'; text: string }

/**
 * Ordered, typed rows — one projection step per source event. Warnings without a
 * round prefix land at the end; the Artifacts raw log is the ground truth (§7.9).
 */
export function streamItems(state: RunState): StreamItem[] {
  const items: StreamItem[] = []
  const roundStages = state.stages.filter((stage) => stage.stage === 'round')
  for (const stage of roundStages) {
    const round = typeof stage.fields.round === 'number' ? stage.fields.round : 0
    items.push({ kind: 'round-header', round, pairs: typeof stage.fields.pairs === 'number' ? stage.fields.pairs : 0, at: stage.at })
    const runRound = state.rounds.find((entry) => entry.round === round)
    if (runRound) for (const turn of runRound.turns) items.push({ kind: 'turn', round, turn })
    const commit = state.commits.find((entry) => entry.round === round)
    if (commit) items.push({ kind: 'commit', ...commit })
    for (const activation of state.activations.filter((entry) => entry.round === round)) {
      items.push({ kind: 'activation', round: activation.round, agents: activation.agents, reasons: activation.reasons })
    }
  }
  for (const [pairId, pair] of Object.entries(state.livePairs)) {
    items.push({ kind: 'pending', pairId, a: pair.a, b: pair.b })
  }
  for (const warning of state.warnings) items.push({ kind: 'warning', text: warning })
  return items
}

// ---------------------------------------------------------------------------
// Verdict (§7.7)
// ---------------------------------------------------------------------------

export interface VerdictView {
  title: string | null
  markdown: string | null
  reportStatus: ReportStatus
  sources: ReportSources
  warnings: string[]
}

export function verdictView(state: RunState): VerdictView | null {
  const verdict = state.verdict
  if (!verdict) return null
  return {
    title: verdict.title,
    markdown: verdict.markdown,
    reportStatus: verdict.reportStatus,
    sources: verdict.sources,
    warnings: state.warnings,
  }
}

