import type { ConsensusInfo, RunEvent, Stance } from '../run/events'

export interface IngestedDoc {
  document_id: string
  title: string
  text: string
  word_count: number
  source_type: 'file' | 'url' | 'text'
  mime_type?: string
  pages?: number
}

export interface IngestFailure {
  filename: string
  status_code: number
  detail: string
}

export interface IngestResponse {
  documents: IngestedDoc[]
  failures: IngestFailure[]
}

export interface DebateConfig {
  max_agents: number
  max_rounds: number
  comm_radius: number
  min_entity_overlap: number
  max_pairs_per_round: number
  convergence_threshold: number
  llm_concurrency: number
  topology_score_threshold: number
  max_new_agents_per_round: number
  snapshot_top_k: number
}

export const DEBATE_CONFIG_DEFAULTS: DebateConfig = {
  max_agents: 50,
  max_rounds: 5,
  comm_radius: 1,
  min_entity_overlap: 1,
  max_pairs_per_round: 50,
  convergence_threshold: 0.8,
  llm_concurrency: 8,
  topology_score_threshold: 0.15,
  max_new_agents_per_round: 2,
  snapshot_top_k: 8,
}

/** Field ranges = `DebateConfig.__post_init__` (backend truth), not the rounder spec notes. */
export const DEBATE_CONFIG_RANGES: Record<keyof DebateConfig, { min: number; max: number; step?: number }> = {
  max_agents: { min: 1, max: 100 },
  max_rounds: { min: 1, max: 20 },
  comm_radius: { min: 1, max: 5 },
  min_entity_overlap: { min: 1, max: 10 },
  max_pairs_per_round: { min: 1, max: 200 },
  convergence_threshold: { min: 0, max: 1, step: 0.05 },
  llm_concurrency: { min: 1, max: 32 },
  topology_score_threshold: { min: 0, max: 1, step: 0.05 },
  max_new_agents_per_round: { min: 0, max: 10 },
  snapshot_top_k: { min: 5, max: 20 },
}

export interface GraphJobResult {
  dataset_id: string
  chunks_total: number
  chunks_completed: number
  docs_built: number
  entity_types: string[]
  relation_types: string[]
}

export interface JobStatus {
  job_id: string
  mode?: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  stage: string
  progress: number
  error?: string | null
  result?: GraphJobResult | null
}

export interface DebateStartRequest {
  graph_id: string
  query: string
  selected_domains: string[]
  simulation_depth: 'shallow' | 'standard' | 'deep'
  config: DebateConfig
}

export interface DebateStatus {
  job_id: string
  status: 'queued' | 'running' | 'complete' | 'failed'
  result?: Record<string, unknown> | null
  error?: string | null
}

export interface RunSummary {
  run_id: string
  created_at: string
  query: string
  dataset_id: string
  status: 'queued' | 'running' | 'complete' | 'failed' | 'interrupted'
  rounds_executed: number
  converged: boolean | null
  verdict_stance: Stance | null
}

export interface RunDoc {
  run_id: string
  created_at: string
  query: string
  dataset_id: string
  config: DebateConfig
  status: string
  events: RunEvent[]
  result?: Record<string, unknown> | null
}

export type { ConsensusInfo }
