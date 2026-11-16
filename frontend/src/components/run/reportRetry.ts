import { ApiError } from '../../api/rest'

/** How often a retry's job is read, and how many reads it gets before the reader stops waiting. */
export const RETRY_POLL_MS = 2000
export const RETRY_MAX_POLLS = 60

/** Every line the retry shows. Constants only: the server's text is never echoed, only its status and code are read. */
export const RETRY_COPY = {
  notProduced: 'The report could not be produced. The run is unchanged; you can retry again.',
  stillNotProduced: 'The report is still not produced. The run is unchanged; you can retry again.',
  slow: 'The retry is taking longer than expected. Reopen this run shortly.',
  failed: 'The report could not be retried. Try again shortly.',
  busy: 'Too many retries. Wait a moment, then try again.',
  units: 'Your usage for this period is used up, so the retry cannot start.',
  forbidden: 'This account cannot retry this report.',
  notPending: 'This run has no report that was not produced, so there is nothing to retry.',
  notRetryable: 'This run kept no inputs for a retry, so its report cannot be retried.',
  inFlight: 'A retry for this report is already queued or running.',
} as const

/** The 409 refusals the server names by code, each with its own constant line. */
const REFUSAL_COPY = new Map<string, string>([
  ['report_not_pending', RETRY_COPY.notPending],
  ['report_not_retryable', RETRY_COPY.notRetryable],
  ['retry_in_progress', RETRY_COPY.inFlight],
])

/** The line a retry leaves under its button, read from the HTTP status and the error code only. */
export function retryMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 402) return RETRY_COPY.units
    if (error.status === 403) return RETRY_COPY.forbidden
    if (error.status === 429) return RETRY_COPY.busy
    if (error.status === 409 && error.code !== null) return REFUSAL_COPY.get(error.code) ?? RETRY_COPY.failed
  }
  return RETRY_COPY.failed
}

/** A polled job's status as the retry reader acts on it: keep waiting, done, or not produced. */
export function retryOutcome(status: string): 'waiting' | 'complete' | 'failed' {
  if (status === 'complete' || status === 'completed') return 'complete'
  if (status === 'failed' || status === 'cancelled') return 'failed'
  return 'waiting'
}

/**
 * The job a retry queued in this session, by run id, so a return to the report resumes polling it
 * instead of leaving the button free while the server is still working. Forgotten once it settles.
 */
const queuedRetries = new Map<string, string>()
export const rememberRetry = (runId: string, jobId: string): void => {
  queuedRetries.set(runId, jobId)
}
export const knownRetry = (runId: string): string | null => queuedRetries.get(runId) ?? null
export const forgetRetry = (runId: string): void => {
  queuedRetries.delete(runId)
}
