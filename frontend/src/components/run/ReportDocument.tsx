import { useEffect, useRef, useState } from 'react'
import { getJob, retryVerdictReport } from '../../api/rest'
import WarningList from '../common/WarningList'
import Button from '../ui/Button'
import Label from '../ui/Label'
import AnswerDocument from './AnswerDocument'
import type { ReportModel } from './exportReport'
import {
  RETRY_MAX_POLLS,
  RETRY_POLL_MS,
  RETRY_SLOW_COPY,
  failedRetryMessage,
  retryMessage,
  retryOutcome,
} from './reportRetry'

/**
 * The Report tab's document. A produced report is the backend's markdown as given; a report that was
 * not produced says so and offers the one retry. `onRestored` runs once a retry has written the report,
 * so the parent can read the run again.
 */
export default function ReportDocument({
  report,
  runId,
  onRestored,
}: {
  report: ReportModel
  runId: string
  onRestored: () => void
}) {
  return (
    <div className="max-w-[760px] space-y-6">
      {report.markdown !== null ? (
        <AnswerDocument runId={runId} markdown={report.markdown} sources={report.sources} />
      ) : (
        <NotProduced runId={runId} onRestored={onRestored} />
      )}
      {report.warnings.length > 0 ? (
        <section className="border-t border-rule pt-6">
          <Label as="h3">Warnings</Label>
          <div className="mt-3">
            <WarningList warnings={report.warnings} />
          </div>
        </section>
      ) : null}
    </div>
  )
}

/** The not-produced state: the retry is queued as a job, polled a bounded number of times, then the run is read again. */
function NotProduced({ runId, onRestored }: { runId: string; onRestored: () => void }) {
  const [busy, setBusy] = useState(false)
  const [jobId, setJobId] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const restored = useRef(onRestored)
  useEffect(() => {
    restored.current = onRestored
  })

  useEffect(() => {
    if (jobId === null) return
    let cancelled = false
    let polls = 0
    let timer: ReturnType<typeof setTimeout> | undefined
    const settle = (text: string | null) => {
      setJobId(null)
      setBusy(false)
      setMessage(text)
    }
    const check = async () => {
      polls += 1
      const job = await getJob(jobId).catch((error: unknown) => {
        if (!cancelled) settle(retryMessage(error))
        return null
      })
      if (job === null || cancelled) return
      const outcome = retryOutcome(job.status)
      if (outcome === 'complete') {
        settle(null)
        restored.current()
      } else if (outcome === 'failed') {
        settle(failedRetryMessage(job.error))
      } else if (polls >= RETRY_MAX_POLLS) {
        settle(RETRY_SLOW_COPY)
      } else {
        timer = setTimeout(check, RETRY_POLL_MS)
      }
    }
    timer = setTimeout(check, RETRY_POLL_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [jobId])

  const retry = async () => {
    setBusy(true)
    setMessage(null)
    try {
      const accepted = await retryVerdictReport(runId)
      setJobId(accepted.job_id)
    } catch (error) {
      setBusy(false)
      setMessage(retryMessage(error))
    }
  }

  return (
    <section className="rounded-xl bg-paper p-12 shadow-sheet">
      <Label as="h3">Report not produced</Label>
      <p className="mt-3 max-w-[60ch] font-ui text-body text-ink-2">
        The report for this decision could not be written. The run is unchanged.
      </p>
      <div className="mt-6">
        <Button type="button" onClick={() => void retry()} disabled={busy}>
          {busy ? 'Retrying…' : 'Retry report'}
        </Button>
      </div>
      {message !== null ? (
        <p role="status" className="mt-3 font-ui text-body-sm text-ink-2">
          {message}
        </p>
      ) : null}
    </section>
  )
}
