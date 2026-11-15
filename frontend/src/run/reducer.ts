import type { DebateConfig } from '../api/types'
import { InvalidAgentError, UnknownStanceError, asStance, parseAgentView, parsePairId } from './events'
import type { AgentView, ClusterSummary, ConsensusInfo, DissentingView, EvidenceItem, PairInfo, QueryIntent, RunEvent, SelectionRow, Stance, TurnInfo, WrittenLink, WrittenNode } from './events'

export interface StageEntry {
  stage: string
  index: number
  at: number
  fields: Record<string, unknown>
}

export interface RunRound {
  round: number
  pairs: PairInfo[]
  turns: TurnInfo[]
  consensus: ConsensusInfo | null
}

export interface RunCommit {
  round: number
  opinions: number
  edges: number
  failed: boolean
  /** The entries the transaction wrote, retained verbatim so the map recomposes from state (D7). */
  writtenNodes: WrittenNode[]
  /** The connections the transaction wrote, retained verbatim. */
  writtenLinks: WrittenLink[]
}

export interface RunActivation {
  round: number
  agents: string[]
  reasons: Record<string, string>
}

export interface RunVerdict {
  converged: boolean
  summary: string
  narrative: string
  /** "ok" | "fallback" — "fallback" means the narrative degraded to `summary` (§17.3). */
  narrativeStatus: string
  dissentingViews: DissentingView[]
  evidence: EvidenceItem[]
  confidence: number | null
  clusters: Record<Stance, ClusterSummary> | null
  finalStances: Record<string, string>
  supporting: string[]
  opposing: string[]
}

export interface RunState {
  runId: string | null
  status: 'queued' | 'running' | 'complete' | 'failed'
  query: string
  datasetId: string | null
  /** Run config rides the run doc (Task 20); null until the doc provides it. */
  config: DebateConfig | null
  stages: StageEntry[]
  intent: QueryIntent | null
  roster: AgentView[]
  rosterTotal: number | null
  selection: SelectionRow[]
  rounds: RunRound[]
  /** In-flight/completed pair turns since the last round event, keyed by pair_id. */
  livePairs: Record<string, { a: string; b: string; startedAt: number }>
  commits: RunCommit[]
  activations: RunActivation[]
  verdict: RunVerdict | null
  warnings: string[]
  error: string | null
  lastIndex: number
  /**
   * Monotonic count of applied events. A cheap primitive invalidation key for derived views — the map
   * composer rebuilds against `version`, so a frame that folds a burst of events rebuilds the map once
   * (the store `set`s the folded run once per frame), not once per event.
   */
  version: number
}

export const initialState: RunState = {
  runId: null,
  status: 'queued',
  query: '',
  datasetId: null,
  config: null,
  stages: [],
  intent: null,
  roster: [],
  rosterTotal: null,
  selection: [],
  rounds: [],
  livePairs: {},
  commits: [],
  activations: [],
  verdict: null,
  warnings: [],
  error: null,
  lastIndex: -1,
  version: 0,
}

export const UNKNOWN_STANCE_WARNING = 'Unknown stance from the server; shown as not available.'
export const INVALID_AGENT_WARNING = 'An agent profile from the server does not match the current shape; it was skipped.'
export const VERDICT_STANCE_WARNING = 'The verdict carried a stance outside the closed set; the run is marked failed.'
const VERDICT_STANCE_ERROR = 'The verdict could not be shown: it carried an unknown stance.'

/**
 * Runs a reduction that reads stances or agent fields. A value that fails the closed set or the view
 * shape keeps the base state, adds one warning and drops only that event's contribution; nothing is
 * defaulted to NEUTRAL and the fold continues.
 */
function skipWith(base: RunState, reduce: () => RunState): RunState {
  try {
    return reduce()
  } catch (error) {
    if (error instanceof UnknownStanceError) return { ...base, warnings: withWarning(base.warnings, UNKNOWN_STANCE_WARNING) }
    if (error instanceof InvalidAgentError) return { ...base, warnings: withWarning(base.warnings, INVALID_AGENT_WARNING) }
    throw error
  }
}

/** Adds a warning once: the same text from many skipped events reads as one line. Exact-string, order kept. */
function withWarning(warnings: readonly string[], text: string): string[] {
  return warnings.includes(text) ? [...warnings] : [...warnings, text]
}

/** Folded warnings and the server's list, merged in order with exact duplicates dropped. */
function mergeWarnings(folded: readonly string[], server: readonly string[]): string[] {
  return [...new Set([...folded, ...server])]
}

/** Every stance a verdict carries, read through the closed set. A false means the verdict cannot be shown. */
function verdictStancesKnown(event: Extract<RunEvent, { type: 'complete' }>): boolean {
  try {
    for (const stance of Object.values(event.final_stances ?? {})) asStance(stance)
    for (const stance of Object.keys(event.cluster_details ?? {})) asStance(stance)
    return true
  } catch (error) {
    if (error instanceof UnknownStanceError) return false
    throw error
  }
}

function parseWeights(weights: Record<string, number>): Record<Stance, number> {
  const parsed = {} as Record<Stance, number>
  for (const [stance, share] of Object.entries(weights)) parsed[asStance(stance)] = share
  return parsed
}

function parseConsensus(consensus: ConsensusInfo | null | undefined): ConsensusInfo | null {
  if (!consensus) return null
  return { ...consensus, stance: asStance(consensus.stance), weights: consensus.weights && parseWeights(consensus.weights) }
}

/** Pure and total — unknown events are warnings, never crashes (forward-compatible with backend additions). */
function reduceEvent(state: RunState, event: RunEvent, now: number): RunState {
  const base = state.status === 'queued' && event.type !== 'ping' && event.type !== 'ack' ? { ...state, status: 'running' as const } : state

  switch (event.type) {
    case 'stage': {
      return {
        ...base,
        stages: [...base.stages, { stage: event.stage, index: event.index, at: now, fields: event as unknown as Record<string, unknown> }],
        query: event.stage === 'intake' && typeof event.query === 'string' ? event.query : base.query,
        lastIndex: Math.max(base.lastIndex, event.index),
      }
    }
    case 'intent':
      return { ...base, intent: event.intent }
    case 'selection':
      return { ...base, selection: event.rows }
    case 'agent':
      return skipWith(base, () => ({
        ...base,
        roster: [...base.roster, parseAgentView(event.profile)],
        rosterTotal: event.total,
      }))
    case 'pair_turn': {
      const parsed = parsePairId(event.pair_id)
      if (!parsed) return { ...base, warnings: [...base.warnings, `Unparseable pair id: ${event.pair_id}`] }
      return {
        ...base,
        datasetId: base.datasetId ?? parsed.datasetId,
        livePairs: { ...base.livePairs, [event.pair_id]: { a: parsed.a, b: parsed.b, startedAt: now } },
      }
    }
    case 'round':
      return skipWith(base, () => ({
        ...base,
        rounds: [
          ...base.rounds,
          {
            round: event.round,
            pairs: event.pairs,
            turns: event.turns.map((turn) => ({ ...turn, stance: asStance(turn.stance) })),
            consensus: parseConsensus(event.consensus),
          },
        ],
        livePairs: {},
      }))
    case 'commit':
      return {
        ...base,
        commits: [
          ...base.commits,
          {
            round: event.round,
            opinions: event.opinions,
            edges: event.edges,
            failed: event.failed ?? false,
            writtenNodes: event.written_nodes ?? [],
            writtenLinks: event.written_links ?? [],
          },
        ],
        warnings: event.failed ? [...base.warnings, `Pass ${event.round}: commit failed: ${event.error ?? 'unknown error'}`] : base.warnings,
      }
    case 'activation':
      return { ...base, activations: [...base.activations, { round: event.round, agents: event.agents, reasons: event.reasons }] }
    case 'complete':
      // A verdict with a stance outside the closed set ends the run as failed: it is never shown as NEUTRAL
      // and never left running. The reader sees the warning and the error, live and reopened alike.
      if (!verdictStancesKnown(event)) {
        return { ...base, status: 'failed', error: VERDICT_STANCE_ERROR, warnings: [...base.warnings, VERDICT_STANCE_WARNING] }
      }
      return {
        ...base,
        status: 'complete',
        verdict: {
          converged: event.converged,
          summary: event.verdict,
          narrative: event.narrative ?? '',
          narrativeStatus: event.narrative_status ?? 'ok',
          dissentingViews: event.dissenting_views ?? [],
          evidence: event.evidence ?? [],
          confidence: event.confidence_score ?? null,
          clusters: event.cluster_details ?? null,
          finalStances: Object.fromEntries(Object.entries(event.final_stances ?? {}).map(([agent, stance]) => [agent, asStance(stance)])),
          supporting: event.supporting_entities ?? [],
          opposing: event.opposing_entities ?? [],
        },
        // The complete event's warnings are the server's full list — they replace the streamed deltas.
        warnings: mergeWarnings(base.warnings, event.warnings ?? []),
      }
    case 'error':
      return { ...base, status: 'failed', error: event.error }
    case 'ping':
    case 'ack':
      return base
    default: {
      const unknown = event as { type?: string }
      return { ...base, warnings: [...base.warnings, `Unhandled event type: ${String(unknown.type)}`] }
    }
  }
}

/**
 * The only way state ever advances. Stamps the monotonic `version` — one bump per applied event, so a
 * fold over N events lands on `initial.version + N` however it is batched (§11.2).
 */
export function applyEvent(state: RunState, event: RunEvent, now: number): RunState {
  return { ...reduceEvent(state, event, now), version: state.version + 1 }
}

/** The only way state is ever built — live WS fold and reopened run docs go through the same path (§11.2). */
export function fold(events: RunEvent[], now: () => number = Date.now): RunState {
  return events.reduce((state, event) => applyEvent(state, event, now()), initialState)
}
