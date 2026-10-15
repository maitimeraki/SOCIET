import type {
  DebateConfig,
  DebateStartRequest,
  DebateStatus,
  IngestedDoc,
  IngestResponse,
  JobStatus,
  RunDoc,
  RunSummary,
  User,
} from './types'
import type { ConsensusInfo } from '../run/events'
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
  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
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
      if (body.detail !== undefined) detail = String(body.detail)
    } catch {
      // Non-JSON error body: keep statusText.
    }
    throw new ApiError(response.status, detail)
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
  return request<IngestResponse>('/api/v1/ingest/files', { method: 'POST', body: form })
}

export const ingestUrl = (url: string) =>
  request<{ document: IngestedDoc }>('/api/v1/ingest/url', jsonInit('POST', { url }))

export const startOntology = (datasetId: string, docs: IngestedDoc[]) =>
  request<{ job_id: string }>(`/api/v1/simulate/ontology?dataset_id=${encodeURIComponent(datasetId)}`, jsonInit('POST', docs))

export const startGraphBuild = (datasetId: string, docs: IngestedDoc[], ontologyJobId?: string) =>
  request<{ job_id: string }>(
    `/api/v1/simulate/build_graph?dataset_id=${encodeURIComponent(datasetId)}${ontologyJobId ? `&ontology_job_id=${encodeURIComponent(ontologyJobId)}` : ''}`,
    jsonInit('POST', docs),
  )

export const getJob = (jobId: string) => request<JobStatus>(`/api/v1/simulate/jobs/${jobId}`)

export const startDebate = (body: DebateStartRequest) =>
  request<{ job_id: string }>('/api/v1/simulate/debate', jsonInit('POST', body))

export const getDebate = (jobId: string) => request<DebateStatus>(`/api/v1/simulate/${jobId}`)

export const listRuns = () => request<RunSummary[]>('/api/v1/simulate/debates')

export const getRun = (runId: string) => request<RunDoc>(`/api/v1/simulate/debates/${runId}`)

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
