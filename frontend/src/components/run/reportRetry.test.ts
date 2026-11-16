import { describe, expect, it } from 'vitest'
import { ApiError, NetworkError } from '../../api/rest'
import { NOT_PRODUCED_COPY, failedRetryMessage, retryMessage, retryOutcome } from './reportRetry'

describe('retryMessage — a refused or failed retry says why, in the server’s own words where it has them', () => {
  it('shows the owner the refusal the server wrote (not produced, not retryable, in flight, units used up)', () => {
    expect(retryMessage(new ApiError(409, 'A retry for this report is already queued or running.'))).toBe(
      'A retry for this report is already queued or running.',
    )
    expect(retryMessage(new ApiError(402, 'Units used up. They reset on 2026-12-01.'))).toBe(
      'Units used up. They reset on 2026-12-01.',
    )
  })

  it('asks the owner to wait on a rate limit', () => {
    expect(retryMessage(new ApiError(429, 'Too many requests'))).toBe('Too many retries. Wait a moment, then try again.')
  })

  it('reads every other failure, including a flat not-found, the same calm way', () => {
    expect(retryMessage(new ApiError(404, 'Not found.'))).toBe('The report could not be retried. Try again shortly.')
    expect(retryMessage(new NetworkError())).toBe('The report could not be retried. Try again shortly.')
  })
})

describe('retryOutcome — the polled job either keeps running or settles', () => {
  it('waits on every live state and settles on the terminal ones', () => {
    expect(retryOutcome('queued')).toBe('waiting')
    expect(retryOutcome('running')).toBe('waiting')
    expect(retryOutcome('complete')).toBe('complete')
    expect(retryOutcome('completed')).toBe('complete')
    expect(retryOutcome('failed')).toBe('failed')
    expect(retryOutcome('cancelled')).toBe('failed')
  })
})

describe('failedRetryMessage — a failed job shows its authored line, or the report’s own', () => {
  it('shows the job’s error when it carries one', () => {
    expect(failedRetryMessage('The report could not be produced. The run is unchanged; you can retry again.')).toBe(
      'The report could not be produced. The run is unchanged; you can retry again.',
    )
  })

  it('falls back to the report’s line when the job carries none', () => {
    expect(failedRetryMessage(null)).toBe(NOT_PRODUCED_COPY)
    expect(failedRetryMessage('')).toBe(NOT_PRODUCED_COPY)
  })
})
