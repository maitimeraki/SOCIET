import { describe, expect, it } from 'vitest'
import { ApiError, NetworkError } from '../../api/rest'
import { RETRY_COPY, forgetRetry, knownRetry, rememberRetry, retryMessage, retryOutcome } from './reportRetry'

describe('retryMessage — the line is read from the status and the code, never from the server’s text', () => {
  it('names each 409 refusal by its code', () => {
    expect(retryMessage(new ApiError(409, 'x', null, 'report_not_pending'))).toBe(RETRY_COPY.notPending)
    expect(retryMessage(new ApiError(409, 'x', null, 'report_not_retryable'))).toBe(RETRY_COPY.notRetryable)
    expect(retryMessage(new ApiError(409, 'x', null, 'retry_in_progress'))).toBe(RETRY_COPY.inFlight)
  })

  it('does not echo the server’s detail text, even on a refusal it recognises', () => {
    const echoed = retryMessage(new ApiError(409, 'SECRET server text', null, 'report_not_pending'))
    expect(echoed).not.toContain('SECRET')
    expect(echoed).toBe(RETRY_COPY.notPending)
  })

  it('falls back to the fixed failure line for an unknown 409 code, or a 409 with none', () => {
    expect(retryMessage(new ApiError(409, 'x', null, 'something_new'))).toBe(RETRY_COPY.failed)
    expect(retryMessage(new ApiError(409, 'x', null, null))).toBe(RETRY_COPY.failed)
  })

  it('maps units used up (402), forbidden (403) and rate limit (429) by status alone', () => {
    expect(retryMessage(new ApiError(402, 'Units used up. They reset on 2026-12-01.', null, null))).toBe(RETRY_COPY.units)
    expect(retryMessage(new ApiError(403, 'raw text', null, null))).toBe(RETRY_COPY.forbidden)
    expect(retryMessage(new ApiError(429, 'Too many', 30, null))).toBe(RETRY_COPY.busy)
  })

  it('reads every other failure, including a flat not-found and a network error, the same calm way', () => {
    expect(retryMessage(new ApiError(404, 'Not found.'))).toBe(RETRY_COPY.failed)
    expect(retryMessage(new NetworkError())).toBe(RETRY_COPY.failed)
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

describe('the queued retry this session remembers, so a return resumes its polling', () => {
  it('remembers the job by run, and forgets it once it settles', () => {
    rememberRetry('run-a', 'job-1')
    expect(knownRetry('run-a')).toBe('job-1')
    expect(knownRetry('run-b')).toBeNull()
    forgetRetry('run-a')
    expect(knownRetry('run-a')).toBeNull()
  })
})
