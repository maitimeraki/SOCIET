import { ApiError, getJob } from './rest'
import type { JobStatus } from './types'

const TERMINAL = new Set(['completed', 'failed'])

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

export interface PollOptions {
  intervalMs?: number
  /** Called with the stretched interval after each network failure. */
  onBackoff?: (delayMs: number) => void
  /** Called when a poll succeeds again after failures. */
  onRecover?: () => void
}

/** Poll a job until completed/failed. 1.5s fixed; network failure backs off ×2 up to 6s and keeps trying (§7.3). */
export async function pollJob(
  jobId: string,
  onTick: (job: JobStatus) => void,
  options: PollOptions = {},
): Promise<JobStatus> {
  const base = options.intervalMs ?? 1500
  let delay = base
  for (;;) {
    try {
      const job = await getJob(jobId)
      if (delay !== base) options.onRecover?.()
      delay = base
      onTick(job)
      if (TERMINAL.has(job.status)) return job
    } catch (error) {
      if (error instanceof ApiError) throw error // server answered — a rejected job id will never get better
      delay = Math.min(delay * 2, 6000)
      options.onBackoff?.(delay)
    }
    await sleep(delay)
  }
}
