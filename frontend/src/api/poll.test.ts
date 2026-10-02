import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from './rest'
import { pollJob } from './poll'
import type { JobStatus } from './types'

// vitest runs in the node environment; poll.ts sleeps via window.setTimeout.
beforeEach(() => {
  vi.stubGlobal('window', { setTimeout })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

const job = (patch: Partial<JobStatus>): JobStatus => ({
  job_id: 'job-1',
  status: 'running',
  stage: 'build_graph',
  progress: 0,
  ...patch,
})

const jsonResponse = (body: unknown) => new Response(JSON.stringify(body))

describe('pollJob', () => {
  it('ticks each poll and resolves with the terminal job', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(job({ progress: 0.2 })))
      .mockResolvedValueOnce(jsonResponse(job({ progress: 0.6 })))
      .mockResolvedValueOnce(jsonResponse(job({ status: 'completed', progress: 1 })))
    vi.stubGlobal('fetch', fetchMock)

    const ticks: JobStatus[] = []
    const final = await pollJob('job-1', (tick) => ticks.push(tick), { intervalMs: 1 })

    expect(ticks.map((tick) => tick.progress)).toEqual([0.2, 0.6, 1])
    expect(final.status).toBe('completed')
  })

  it('rejects on ApiError without retrying — a rejected job id never gets better', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'job not found' }), { status: 404 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(pollJob('missing', () => {}, { intervalMs: 1 })).rejects.toBeInstanceOf(ApiError)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('backs off on network failure and recovers', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('fetch failed'))
      .mockResolvedValueOnce(jsonResponse(job({ status: 'completed' })))
    vi.stubGlobal('fetch', fetchMock)

    const onBackoff = vi.fn()
    const onRecover = vi.fn()
    const final = await pollJob('job-1', () => {}, { intervalMs: 1, onBackoff, onRecover })

    expect(onBackoff).toHaveBeenCalledWith(2)
    expect(onRecover).toHaveBeenCalledTimes(1)
    expect(final.status).toBe('completed')
  })
})
