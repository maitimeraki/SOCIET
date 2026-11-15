export type Stance = 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL' | 'ABSTAIN'

export class UnknownStanceError extends Error {}

/** Parse a backend stance string to the closed set. Anything else throws; it is never read as NEUTRAL. */
export function asStance(value: string): Stance {
  const upper = value.toUpperCase()
  if (upper === 'POSITIVE' || upper === 'NEGATIVE' || upper === 'NEUTRAL' || upper === 'ABSTAIN') return upper
  throw new UnknownStanceError(`Unknown stance "${value}"`)
}

export interface QueryIntent {
  direct_keywords: string[]
  latent_sectors: string[]
  search_perspectives: string[]
  core_question: string
  domain_tags: string[]
  entity_frame: string[]
  stance_axis: string
  extraction_confidence: number
}

export interface SelectionRow {
  name: string
  semantic: number
  density: number
  blended: number
  anchors?: Record<string, string>[]
}

/** The one agent shape the backend sends. Nothing else about an agent reaches the client. */
export interface AgentView {
  name: string
  /** Free-text entity type; may be the literal "type unknown". Render as is. */
  type: string
  role: string
  stance: Stance
  /** Mean strength of the agent's position, 0..1. */
  strength: number
  bio: string
  details: string
  confidence: number
}

export interface PairInfo {
  agent_a: string
  agent_b: string
  shared_entities: string[]
}

export interface TurnInfo {
  agent_id: string
  agent_name: string
  content: string
  stance: string
  confidence: number
  references: string[]
}

export interface ConsensusInfo {
  stance: string
  weight_share: number
  threshold: number
  /** Per-stance normalized weight share for this round (sums to 1). Backend §12.3 item 3. */
  weights?: Record<Stance, number>
}

export interface ClusterSummary {
  stance: Stance
  count: number
  total_weight: number
  avg_confidence: number
  /** Wire name kept; the value is the mean agent strength (not conviction). */
  avg_conviction: number
  agents: string[]
}

export interface DissentingView {
  stance: string
  view: string
}

/**
 * An entry a `commit` event reports the transaction wrote — taken verbatim (D7). `key` is the
 * identity the write MERGEs under, `label` the entry's kind, `name` its short display label.
 */
export interface WrittenNode {
  key: string
  label: string
  name: string
}

/**
 * A connection a `commit` event reports the transaction wrote — taken verbatim (D7). `from`/`to`
 * are the endpoints' keys as the backend writes them, `kind` the relation name.
 */
export interface WrittenLink {
  from: string
  to: string
  kind: string
}

export interface EvidenceItem {
  entity: string
  claim: string
}

export type RunEvent =
  | {
      type: 'stage'
      stage: 'intake' | 'selection' | 'synthesis' | 'round' | 'convergence' | 'verdict'
      index: number
      round?: number
      pairs?: number
      turns?: number
      agents?: number
      converged?: boolean
      rounds_executed?: number
      share?: number
      threshold?: number
      query?: string
    }
  | { type: 'intent'; intent: QueryIntent }
  | { type: 'selection'; rows: SelectionRow[] }
  | { type: 'agent'; profile: AgentView; index: number; total: number }
  | { type: 'pair_turn'; pair_id: string; response: string | null; error: string | null }
  | { type: 'round'; round: number; pairs: PairInfo[]; turns: TurnInfo[]; consensus?: ConsensusInfo | null }
  | {
      type: 'commit'
      round: number
      opinions: number
      edges: number
      /** The entries the transaction wrote, verbatim — the map mirrors stored truth (D7). */
      written_nodes?: WrittenNode[]
      /** The connections the transaction wrote, verbatim. */
      written_links?: WrittenLink[]
      failed?: boolean
      error?: string
    }
  | { type: 'activation'; round: number; agents: string[]; reasons: Record<string, string> }
  | {
      type: 'complete'
      converged: boolean
      verdict: string
      /** Query-grounded markdown answer; empty when synthesis fell back to `verdict`. */
      narrative?: string
      /** "ok" when `narrative` is the query-grounded answer; "fallback" when it degraded to `verdict`. */
      narrative_status?: string
      dissenting_views?: DissentingView[]
      evidence?: EvidenceItem[]
      final_stances: Record<string, string>
      warnings: string[]
      rounds_executed: number
      confidence_score?: number
      cluster_details?: Record<Stance, ClusterSummary>
      supporting_entities?: string[]
      opposing_entities?: string[]
    }
  | { type: 'error'; error: string }
  | { type: 'ping' }
  | { type: 'ack' }

/** `pair_id` is `"{dataset_id}:{agent_a}:{agent_b}"` — names may contain colons, so only the dataset prefix is stripped blindly (names never do). */
export function parsePairId(pairId: string): { datasetId: string; a: string; b: string } | null {
  const parts = pairId.split(':')
  if (parts.length < 3) return null
  return { datasetId: parts[0], a: parts[1], b: parts.slice(2).join(':') }
}
