import { Link } from 'react-router-dom'

export interface WorkingRun {
  runId: string
  question: string
  passes: string
  note: string
  convergence: number | null
}

export interface WorkingNowProps {
  run: WorkingRun | null
}

/**
 * §7.8 — what is still running. A convergence tape is a measurement, not a progress bar for
 * its own sake: a rule with a fill and a mono percentage. The section stays on the page when
 * nothing runs — it is one of the five, and its quiet state says so in one line.
 */
export default function WorkingNow({ run }: WorkingNowProps) {
  return (
    <section className="rounded-lg bg-paper p-5 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Working now</p>
        {run ? (
          <span className="inline-flex min-h-6 items-center gap-1.5 rounded-xs bg-sand px-2 font-mono text-micro uppercase tracking-[0.04em] text-warn">
            <i className="h-1.5 w-1.5 rounded-full bg-warn" />Deliberating
          </span>
        ) : null}
      </div>
      {run ? (
        <>
          <h2 className="mt-3 font-display text-heading font-medium tracking-[-0.02em] text-ink">{run.question}</h2>
          <p className="mt-2 font-ui text-body-sm text-ink-2">{run.note}</p>
          <div className="mt-4 flex items-center justify-between gap-3 font-mono text-micro text-ink-3">
            <span>Convergence</span>
            <span className="font-mono text-body-sm text-ink">{run.convergence === null ? '—' : run.convergence.toFixed(2)}</span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-sand">
            <span className="block h-full rounded-full bg-accent" style={{ width: `${Math.round((run.convergence ?? 0) * 100)}%` }} />
          </div>
          <p className="mt-3">
            <Link to={`/runs/${run.runId}`} className="font-ui text-body-sm text-accent underline underline-offset-4">
              Open the run
            </Link>
          </p>
          <p className="mt-2 font-mono text-micro text-ink-3">pass {run.passes}</p>
        </>
      ) : (
        <p className="mt-3 font-ui text-body-sm text-ink-2">
          Nothing is running. The next question you ask appears here while the panel works.
        </p>
      )}
    </section>
  )
}
