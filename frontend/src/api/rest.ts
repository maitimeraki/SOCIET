import type {
  DebateConfig,
  DebateStartRequest,
  DebateStatus,
  IngestedDoc,
  IngestResponse,
  JobStatus,
  RunDoc,
  RunSummary,
} from './types'
import type { ConsensusInfo } from '../run/events'

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, init)
  } catch {
    throw new NetworkError()
  }
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (body.detail !== undefined) detail = String(body.detail)
    } catch {
      // Non-JSON error body: keep statusText.
    }
    throw new ApiError(response.status, detail)
  }
  return (await response.json()) as T
}

const jsonInit = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const health = () =>
  request<{ status: string; version: string; active_jobs: number }>('/health')

export const ingestFiles = (files: File[]) => {
  const form = new FormData()
  for (const file of files) form.append('files', file)
  return request<IngestResponse>('/api/ingest/files', { method: 'POST', body: form })
}

export const ingestUrl = (url: string) =>
  request<{ document: IngestedDoc }>('/api/ingest/url', jsonInit('POST', { url }))

export const startOntology = (datasetId: string, docs: IngestedDoc[]) =>
  request<{ job_id: string }>(`/simulate/ontology?dataset_id=${encodeURIComponent(datasetId)}`, jsonInit('POST', docs))

export const startGraphBuild = (datasetId: string, docs: IngestedDoc[]) =>
  request<{ job_id: string }>(`/simulate/build_graph?dataset_id=${encodeURIComponent(datasetId)}`, jsonInit('POST', docs))

export const getJob = (jobId: string) => request<JobStatus>(`/simulate/jobs/${jobId}`)

export const startDebate = (body: DebateStartRequest) =>
  request<{ job_id: string }>('/simulate/debate', jsonInit('POST', body))

export const getDebate = (jobId: string) => request<DebateStatus>(`/simulate/${jobId}`)

export const listRuns = () => request<RunSummary[]>('/simulate/debates')

export const getRun = (runId: string) => request<RunDoc>(`/simulate/debates/${runId}`)

export type { DebateConfig, ConsensusInfo }
