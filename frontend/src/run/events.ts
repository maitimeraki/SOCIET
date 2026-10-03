export type Stance = 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL' | 'AMBIVALENT'

/** Coerce an arbitrary backend stance string to the closed set — unknown values read as NEUTRAL. */
export function asStance(value: string): Stance {
  return value === 'POSITIVE' || value === 'NEGATIVE' || value === 'AMBIVALENT' ? value : 'NEUTRAL'
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
  llm_model?: string
  llm_provider?: string
}

export interface SelectionRow {
  name: string
  semantic: number
  density: number
  blended: number
  anchors?: Record<string, string>[]
}

export interface ProvenanceLink {
  doc_id: string
  title: string
  breadcrumb?: string
  chunk_id: string
}

export interface ConfidenceBreakdown {
  source_breadth: number
  node_density: number
  relationship_connectivity: number
}

export interface AgentProfile {
  agent_id: string
  identity: { name: string; archetype: string; communication_style: string }
  bio: string
  detailed_perspective: string
  role_description?: string
  discovery_type?: string
  expertise_level?: string
  stance: Stance
  intensity: number
  confidence: number
  conviction: number
  cior: number
  domain_tags: string[]
  instinct_tags?: string[]
  entity_affinity?: string[]
  communication_radius: number
  summary_provenance: ProvenanceLink[]
  confidence_breakdown: ConfidenceBreakdown
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
  avg_conviction: number
  agents: string[]
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
  | { type: 'agent'; profile: AgentProfile; index: number; total: number }
  | { type: 'pair_turn'; pair_id: string; response: string | null; error: string | null }
  | { type: 'round'; round: number; pairs: PairInfo[]; turns: TurnInfo[]; consensus?: ConsensusInfo | null }
  | { type: 'commit'; round: number; opinions: number; edges: number; failed?: boolean; error?: string }
  | { type: 'activation'; round: number; agents: string[]; reasons: Record<string, string> }
  | {
      type: 'complete'
      converged: boolean
      verdict: string
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
