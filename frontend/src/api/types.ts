import type { ConsensusInfo, RunEvent, Stance } from '../run/events'

/** `GET /api/v1/auth/me` / login / signup response — the backend's `UserOut`. */
export interface User {
  id: string
  email: string
  created_at: string
  role: 'user' | 'support' | 'admin'
  plan: string
  entitlements: {
    max_agents: number
    max_rounds: number
    units_remaining: number
    period_end: string
  }
}

/** `GET /api/v1/billing/usage` — the server's only usage figures; the client invents none. */
export interface BillingUsage {
  plan: string
  units_total: number
  units_used: number
  units_remaining: number
  period_start: string
  period_end: string
  limits: { max_agents: number; max_rounds: number }
  billing_enabled: boolean
}

/** `GET /api/v1/legal/documents` — one current version per slug, no content. */
export interface LegalDocumentMeta {
  slug: string
  version: string
  effective_at: string
  content_sha256: string
}

/** `GET /api/v1/legal/documents/{slug}` — the metadata plus the served statutory text. */
export interface LegalDocument extends LegalDocumentMeta {
  content: string
}

export interface IngestedDoc {
  document_id: string
  title: string
  text: string
  word_count: number
  source_type: 'file' | 'url' | 'text'
  mime_type?: string
  pages?: number
}

/** `GET /api/v1/ingest/documents` — one upload's extracted payload; `upload_id` is the row id. */
export interface IngestedDocument extends IngestedDoc {
  upload_id: string
}

/**
 * `GET /api/v1/uploads` — one row per caller-owned upload, newest first. `read` is
 * `extracted_text is not None`; `dataset_name` is null until the upload joins a corpus.
 */
export interface UploadRow {
  id: string
  name: string
  bytes: number
  mime: string
  read: boolean
  dataset_id: string | null
  dataset_name: string | null
  created_at: string
}

/** R17: `POST /api/v1/ingest/files|url` accept the batch and enqueue — extraction is a job. */
export interface IngestAccepted {
  job_id: string
  status: string
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

/** The `extract_upload` job's result (R17) — the upload ids nested under `result`, not at the top. */
export interface IngestJobResult {
  upload_ids?: string[]
}

export interface JobStatus<TResult = GraphJobResult> {
  job_id: string
  mode?: string
  /** `run_doc.TERMINAL_STATUSES` is the truth: complete/completed/failed/cancelled all end a poll. */
  status: 'queued' | 'running' | 'complete' | 'completed' | 'failed' | 'cancelled'
  stage: string
  progress: number
  error?: string | null
  result?: TResult | null
}

export interface DebateStartRequest {
  graph_id: string
  query: string
  /** The client's corpus name, for the run history list — null when no corpus existed (backend Task 1.4). */
  corpus_label: string | null
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
  /** The client's corpus name at start; null when no corpus was named (backend `run_doc._summarize`). */
  corpus_label: string | null
  dataset_id: string
  status: 'queued' | 'running' | 'complete' | 'completed' | 'failed' | 'interrupted' | 'cancelled'
  rounds_executed: number
  converged: boolean | null
  verdict_stance: Stance | null
  /** The filed share — the dominant stance's weighted share. Null when no answer was filed. */
  verdict_confidence: number | null
}

/** `GET /api/v1/simulate/debates` — keyset page (plan §6): `next_cursor` null at the end. */
export interface RunListPage {
  items: RunSummary[]
  next_cursor: string | null
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
