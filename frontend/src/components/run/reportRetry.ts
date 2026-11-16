import { ApiError } from '../../api/rest'

/** How often a retry's job is read, and how many reads it gets before the reader stops waiting. */
export const RETRY_POLL_MS = 2000
export const RETRY_MAX_POLLS = 60

export const NOT_PRODUCED_COPY = 'The report could not be produced. The run is unchanged; you can retry again.'
/** The retry is still running after the reader stopped waiting; the report lands in the run when it does. */
export const RETRY_SLOW_COPY = 'The retry is taking longer than expected. Reopen this run shortly.'
const RETRY_FAILED_COPY = 'The report could not be retried. Try again shortly.'
const RETRY_BUSY_COPY = 'Too many retries. Wait a moment, then try again.'
/** Refusals the server words for the owner (not produced, not retryable, in flight, units used up). */
const AUTHORED_STATUSES = new Set([402, 403, 409])

/** The line a retry leaves under its button when the request is refused or the retry fails. */
export function retryMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (AUTHORED_STATUSES.has(error.status) && error.detail) return error.detail
    if (error.status === 429) return RETRY_BUSY_COPY
  }
  return RETRY_FAILED_COPY
}

/** A polled job's status as the retry reader acts on it: keep waiting, done, or not produced. */
export function retryOutcome(status: string): 'waiting' | 'complete' | 'failed' {
  if (status === 'complete' || status === 'completed') return 'complete'
  if (status === 'failed' || status === 'cancelled') return 'failed'
  return 'waiting'
}

/** A failed job's message: the server's own authored line when it sent one, else the report's. */
export function failedRetryMessage(error: string | null | undefined): string {
  return error || NOT_PRODUCED_COPY
}
