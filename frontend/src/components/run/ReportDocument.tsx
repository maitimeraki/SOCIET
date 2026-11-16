import { useEffect, useRef, useState } from 'react'
import { getJob, retryVerdictReport } from '../../api/rest'
import WarningList from '../common/WarningList'
import Button from '../ui/Button'
import Label from '../ui/Label'
import AnswerDocument from './AnswerDocument'
import type { ReportModel } from './exportReport'
import {
  RETRY_COPY,
  RETRY_MAX_POLLS,
  RETRY_POLL_MS,
  forgetRetry,
  knownRetry,
  rememberRetry,
  retryMessage,
  retryOutcome,
} from './reportRetry'

/**
 * The Report document. A produced report is the backend's markdown as given; a report whose status is
 * `not_produced` says so and offers the one retry. `onRestored` resolves once the parent has read the
 * run again after a retry wrote the report.
 */
export default function ReportDocument({
  report,
  runId,
  onRestored,
}: {
  report: ReportModel
  runId: string
  onRestored: () => Promise<void>
}) {
  return (
    <div className="max-w-[760px] space-y-6">
      {report.reportStatus === 'not_produced' ? (
        <NotProduced key={runId} runId={runId} onRestored={onRestored} />
      ) : report.markdown !== null ? (
        <AnswerDocument runId={runId} markdown={report.markdown} sources={report.sources} />
      ) : null}
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

/**
 * The not-produced state. A retry is queued as a job and polled a bounded number of times. A job that
 * completes reloads the run: if the report is now produced this state leaves the page; if it is not,
 * the state says so. A retry queued earlier in this session resumes its polling on return.
 */
function NotProduced({ runId, onRestored }: { runId: string; onRestored: () => Promise<void> }) {
  const [jobId, setJobId] = useState<string | null>(() => knownRetry(runId))
  const [busy, setBusy] = useState(() => knownRetry(runId) !== null)
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
    const settle = (text: string) => {
      forgetRetry(runId)
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
        try {
          await restored.current()
        } catch {
          // The parent logs its own failed reload; the state below still says what the job did.
        }
        if (!cancelled) settle(RETRY_COPY.stillNotProduced)
      } else if (outcome === 'failed') {
        settle(RETRY_COPY.notProduced)
      } else if (polls >= RETRY_MAX_POLLS) {
        settle(RETRY_COPY.slow)
      } else {
        timer = setTimeout(check, RETRY_POLL_MS)
      }
    }
    timer = setTimeout(check, RETRY_POLL_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [jobId, runId])

  const retry = async () => {
    setBusy(true)
    setMessage(null)
    try {
      const accepted = await retryVerdictReport(runId)
      rememberRetry(runId, accepted.job_id)
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
