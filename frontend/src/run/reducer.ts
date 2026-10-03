import { parsePairId } from './events'
import type { AgentProfile, ClusterSummary, ConsensusInfo, PairInfo, QueryIntent, RunEvent, SelectionRow, Stance, TurnInfo } from './events'

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
}

export interface RunActivation {
  round: number
  agents: string[]
  reasons: Record<string, string>
}

export interface RunVerdict {
  converged: boolean
  summary: string
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
  stages: StageEntry[]
  intent: QueryIntent | null
  roster: AgentProfile[]
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
}

export const initialState: RunState = {
  runId: null,
  status: 'queued',
  query: '',
  datasetId: null,
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
}

/** Pure and total — unknown events are warnings, never crashes (forward-compatible with backend additions). */
export function applyEvent(state: RunState, event: RunEvent, now: number): RunState {
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
      return { ...base, roster: [...base.roster, event.profile], rosterTotal: event.total }
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
      return {
        ...base,
        rounds: [...base.rounds, { round: event.round, pairs: event.pairs, turns: event.turns, consensus: event.consensus ?? null }],
        livePairs: {},
      }
    case 'commit':
      return {
        ...base,
        commits: [...base.commits, { round: event.round, opinions: event.opinions, edges: event.edges, failed: event.failed ?? false }],
        warnings: event.failed ? [...base.warnings, `Round ${event.round}: commit failed: ${event.error ?? 'unknown error'}`] : base.warnings,
      }
    case 'activation':
      return { ...base, activations: [...base.activations, { round: event.round, agents: event.agents, reasons: event.reasons }] }
    case 'complete':
      return {
        ...base,
        status: 'complete',
        verdict: {
          converged: event.converged,
          summary: event.verdict,
          confidence: event.confidence_score ?? null,
          clusters: event.cluster_details ?? null,
          finalStances: event.final_stances ?? {},
          supporting: event.supporting_entities ?? [],
          opposing: event.opposing_entities ?? [],
        },
        // The complete event's warnings are the server's full list — they replace the streamed deltas.
        warnings: event.warnings ?? base.warnings,
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

/** The only way state is ever built — live WS fold and reopened run docs go through the same path (§11.2). */
export function fold(events: RunEvent[], now: () => number = Date.now): RunState {
  return events.reduce((state, event) => applyEvent(state, event, now()), initialState)
}
