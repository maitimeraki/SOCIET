export type Stance = 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL' | 'ABSTAIN'

export class UnknownStanceError extends Error {}

/** A profile that does not match the agent view shape (a pre-3.1 stored row, a missing field). */
export class InvalidAgentError extends Error {}

/** Parse a backend stance to the closed set. Anything else (including a non-string) throws; it is never read as NEUTRAL. */
export function asStance(value: unknown): Stance {
  if (typeof value !== 'string') throw new UnknownStanceError(`Unknown stance ${String(value)}`)
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

/**
 * Project a server agent profile onto AgentView: exactly the view keys, the stance parsed. Throws
 * InvalidAgentError when a field is missing or mistyped (a pre-3.1 row, say) and UnknownStanceError
 * for a stance outside the closed set. Callers skip the profile and say so; nothing is defaulted.
 */
export function parseAgentView(raw: unknown): AgentView {
  if (typeof raw !== 'object' || raw === null) throw new InvalidAgentError('agent profile is not an object')
  const { name, type, role, bio, details, strength, confidence, stance } = raw as Record<string, unknown>
  if (typeof name !== 'string' || typeof type !== 'string' || typeof role !== 'string') throw new InvalidAgentError('agent profile lacks name, type or role')
  if (typeof bio !== 'string' || typeof details !== 'string') throw new InvalidAgentError('agent profile lacks bio or details')
  if (!isFiniteNumber(strength) || !isFiniteNumber(confidence)) throw new InvalidAgentError('agent profile lacks strength or confidence')
  return { name, type, role, stance: asStance(stance), strength, bio, details, confidence }
}

const isFiniteNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)

/** The agent views a run doc's events carry; a profile that does not parse is counted and left out. */
export function rosterFromEvents(events: readonly RunEvent[]): { roster: AgentView[]; skipped: number } {
  const roster: AgentView[] = []
  let skipped = 0
  for (const event of events) {
    if (event.type !== 'agent') continue
    try {
      roster.push(parseAgentView(event.profile))
    } catch (error) {
      if (!(error instanceof InvalidAgentError) && !(error instanceof UnknownStanceError)) throw error
      skipped += 1
    }
  }
  return { roster, skipped }
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
