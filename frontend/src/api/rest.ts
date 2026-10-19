import type {
  DebateConfig,
  DebateStartRequest,
  DebateStatus,
  GraphJobResult,
  IngestAccepted,
  IngestedDoc,
  IngestedDocument,
  JobStatus,
  RunDoc,
  RunListPage,
  RunSummary,
  UploadRow,
  User,
} from './types'
import type { ConsensusInfo } from '../run/events'
import type { GraphSnapshot } from '../graph/graphStore'
import { apiBase, apiBaseError } from '../config/env'

export const API_BASE: string = apiBase ?? ''

export class ConfigError extends Error {
  constructor(detail: string) {
    super(detail)
    this.name = 'ConfigError'
  }
}

export class ApiError extends Error {
  status: number
  detail: string
  /** The `Retry-After` seconds on a 429 (the quota/job-cap rejection), else null. */
  retryAfter: number | null
  constructor(status: number, detail: string, retryAfter: number | null = null) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.retryAfter = retryAfter
  }
}

export class NetworkError extends Error {
  constructor() {
    super(`Couldn't reach the server at ${API_BASE}`)
    this.name = 'NetworkError'
  }
}

/**
 * The 401 seam. `authStore` registers a callback here and `rest.ts` invokes it on any 401 — so the
 * store clears WITHOUT `rest.ts` importing `authStore.ts` (which would be a cycle: the store imports
 * the auth helpers below). Never retry on 401; the guard (15c) owns the redirect.
 */
export type UnauthorizedHandler = () => void
let unauthorizedHandler: UnauthorizedHandler | null = null
export function registerUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler
}

const STATE_CHANGING = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

/**
 * R36: the `csrf` cookie is JS-readable by design — the SPA echoes it as the double-submit header.
 * Defensive: under this repo's node-env vitest there is no `document`, and an unauthenticated client
 * has no cookie — either means "no header", never a throw.
 */
function readCsrfCookie(): string | null {
  if (typeof document === 'undefined') return null
  const match = document.cookie.match(/(?:^|;\s*)csrf=([^;]*)/)
  return match ? decodeURIComponent(match[1]) : null
}

/**
 * The backend's error `detail` is a bare string on the legacy routes and `{code, message}` on the v1
 * ones (422 validation, 429 quota). Read the message when there is one; never stringify an object.
 */
function readDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (detail !== null && typeof detail === 'object' && 'message' in detail) {
    return String((detail as { message: unknown }).message)
  }
  return String(detail)
}

/** A 429's `Retry-After` is delta-seconds; an HTTP-date (or anything non-numeric) reads as null. */
function readRetryAfter(response: Response): number | null {
  const header = response.headers.get('Retry-After')
  if (header === null) return null
  const seconds = Number(header)
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // apiBaseError is non-null exactly when apiBase is null: fail recoverably at call time rather than
  // fetching a bare path that would silently hit the static host. `''` (same-origin) passes through.
  if (apiBaseError !== null) throw new ConfigError(apiBaseError)
  const method = (init?.method ?? 'GET').toUpperCase()
  const headers = new Headers(init?.headers)
  if (STATE_CHANGING.has(method)) {
    const csrf = readCsrfCookie()
    if (csrf !== null) headers.set('X-CSRF-Token', csrf)
  }
  let response: Response
  try {
    // Cookie-only sessions: every request rides the httpOnly `sid` cookie.
    response = await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: 'include' })
  } catch {
    throw new NetworkError()
  }
  if (!response.ok) {
    if (response.status === 401) unauthorizedHandler?.() // session gone — clear, never retry
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (body.detail !== undefined) detail = readDetail(body.detail)
    } catch {
      // Non-JSON error body: keep statusText.
    }
    throw new ApiError(response.status, detail, readRetryAfter(response))
  }
  if (response.status === 204) return undefined as T // logout etc. carry no body
  return (await response.json()) as T
}

const jsonInit = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

// `/health` is a top-level route (not under `/api/v1`); everything else speaks v1 only (R3).
export const health = () =>
  request<{ status: string; version: string; active_jobs: number }>('/health')

export const ingestFiles = (files: File[]) => {
  const form = new FormData()
  for (const file of files) form.append('files', file)
  return request<IngestAccepted>('/api/v1/ingest/files', { method: 'POST', body: form })
}

export const ingestUrl = (url: string) =>
  request<IngestAccepted>('/api/v1/ingest/url', jsonInit('POST', { url }))

/** The extracted payloads for a completed ingest job's upload ids (R17). */
export const getIngestDocuments = (uploadIds: string[]) =>
  request<{ documents: IngestedDocument[] }>(
    `/api/v1/ingest/documents?upload_ids=${encodeURIComponent(uploadIds.join(','))}`,
  )

/** The caller's own uploads, newest first (§8.3 Documents) — `{ items }`, `dataset_name` null until a corpus. */
export const listUploads = () => request<{ items: UploadRow[] }>('/api/v1/uploads')

export const startOntology = (datasetId: string, docs: IngestedDoc[]) =>
  request<{ job_id: string }>(`/api/v1/simulate/ontology?dataset_id=${encodeURIComponent(datasetId)}`, jsonInit('POST', docs))

/** The corpus becomes real on this call: its name rides along, and the server writes the row a run's dataset points at. */
export const startGraphBuild = (datasetId: string, docs: IngestedDoc[], corpusName: string, ontologyJobId?: string) =>
  request<{ job_id: string }>(
    `/api/v1/simulate/build_graph?dataset_id=${encodeURIComponent(datasetId)}&corpus_name=${encodeURIComponent(corpusName)}${ontologyJobId ? `&ontology_job_id=${encodeURIComponent(ontologyJobId)}` : ''}`,
    jsonInit('POST', docs),
  )

/** `/api/v1/jobs/{id}` is the canonical status read (R3); the result shape is the caller's to name. */
export const getJob = <TResult = GraphJobResult>(jobId: string) =>
  request<JobStatus<TResult>>(`/api/v1/jobs/${jobId}`)

export const startDebate = (body: DebateStartRequest) =>
  request<{ job_id: string }>('/api/v1/simulate/debate', jsonInit('POST', body))

export const getDebate = (jobId: string) => request<DebateStatus>(`/api/v1/simulate/${jobId}`)

/** One keyset page of owned runs, newest first — `{items, next_cursor}` (plan §6). */
export const listRunsPage = (options: { limit?: number; cursor?: string | null } = {}) => {
  const params = new URLSearchParams()
  if (options.limit !== undefined) params.set('limit', String(options.limit))
  if (options.cursor) params.set('cursor', options.cursor)
  const query = params.toString()
  return request<RunListPage>(`/api/v1/simulate/debates${query ? `?${query}` : ''}`)
}

/**
 * The first page's items — for callers that want only the newest runs. Capped at **25** (the v1 page
 * size): a caller that needs the full list must walk `listRunsPage` + `next_cursor` itself.
 */
export const listRuns = async (): Promise<RunSummary[]> => (await listRunsPage({ limit: 25 })).items

export const getRun = (runId: string) => request<RunDoc>(`/api/v1/simulate/debates/${runId}`)

/**
 * The run's stored map — its corpus id, every entry and connection, the vocabulary (Task 1.3).
 * Shape-checked against `GraphSnapshot`, so the reopened run seeds the one store from it.
 */
export interface RunGraphSnapshot extends GraphSnapshot {
  dataset_id: string
  chunk_count: number
}

/**
 * A 404 is typed (`no_corpus` / `corpus_gone`): the run never named a corpus, or its corpus is gone.
 * Either way the same ApiError — the caller's answer is the same for both.
 */
export const getRunGraph = (runId: string) =>
  request<RunGraphSnapshot>(`/api/v1/simulate/debates/${runId}/graph`)

export const authMe = () => request<User>('/api/v1/auth/me')

export const authLogin = (email: string, password: string) =>
  request<User>('/api/v1/auth/login', jsonInit('POST', { email, password }))

export const authSignup = (email: string, password: string) =>
  request<User>('/api/v1/auth/signup', jsonInit('POST', { email, password }))

export const authLogout = () => request<void>('/api/v1/auth/logout', { method: 'POST' })

/** Mint a one-time WebSocket ticket (R4) — never a long-lived token, never in a query string but here. */
export const fetchWsTicket = () =>
  request<{ ticket: string; expires_in: number }>('/api/v1/ws-ticket', { method: 'POST' })

export type { DebateConfig, ConsensusInfo, User }
