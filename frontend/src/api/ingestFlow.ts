import { ApiError, getIngestDocuments, ingestFiles, ingestUrl } from './rest'
import { pollJob } from './poll'
import type { IngestedDocument, IngestJobResult, JobStatus } from './types'

/**
 * The R17 ingest transport, shared by the file batch and the URL fetch:
 * `POST /ingest/files|url` → 202 `{job_id, status}` → poll `/api/v1/jobs/{id}` → read
 * `result.upload_ids` → `GET /ingest/documents?upload_ids=…`.
 *
 * The upload ids are NESTED at `result.upload_ids` (the job doc is the whole run document,
 * not a flat `{status, upload_ids}` envelope) — read from there, never invented.
 */
export type IngestOutcome =
  | { kind: 'documents'; documents: IngestedDocument[] }
  | { kind: 'failed'; reason: string }
  | { kind: 'quota'; message: string; retryAfterSeconds: number | null }

function uploadIds(result: IngestJobResult | null | undefined): string[] {
  const ids = result?.upload_ids
  return Array.isArray(ids) ? ids.filter((id): id is string => typeof id === 'string') : []
}

async function attempt(
  submit: () => Promise<{ job_id: string }>,
  onTick?: (job: JobStatus<IngestJobResult>) => void,
): Promise<IngestOutcome> {
  try {
    const accepted = await submit()
    const job = await pollJob<IngestJobResult>(accepted.job_id, onTick ?? (() => {}))
    if (job.status !== 'completed') {
      const reason =
        job.error || (job.status === 'cancelled' ? 'the extraction was cancelled' : 'the extraction did not finish')
      return { kind: 'failed', reason }
    }
    const ids = uploadIds(job.result)
    if (ids.length === 0) return { kind: 'failed', reason: 'the extraction returned no sections' }
    const { documents } = await getIngestDocuments(ids)
    return { kind: 'documents', documents }
  } catch (error) {
    // A 429 is the quota/cap rejection — a distinct state with retry semantics, not a generic failure.
    if (error instanceof ApiError && error.status === 429) {
      return { kind: 'quota', message: error.detail, retryAfterSeconds: error.retryAfter }
    }
    return { kind: 'failed', reason: error instanceof Error ? error.message : 'unknown error' }
  }
}

export const runFileIngest = (files: File[], onTick?: (job: JobStatus<IngestJobResult>) => void) =>
  attempt(() => ingestFiles(files), onTick)

export const runUrlIngest = (url: string, onTick?: (job: JobStatus<IngestJobResult>) => void) =>
  attempt(() => ingestUrl(url), onTick)
