import { Link } from 'react-router-dom'
import PositionMark from '../ui/PositionMark'
import type { Position } from '../ui/PositionMark'

export interface RecentRow {
  runId: string
  question: string
  state: 'Filed' | 'Deliberating' | 'Failed' | 'Interrupted' | 'Cancelled'
  stance: Position | null
  share: number | null
  passes: string
  date: string
}

/** The row's own address: a filed answer opens its verdict; every other state opens the run. */
function rowTarget(row: RecentRow): string {
  return row.state === 'Filed' ? `/runs/${row.runId}/verdict` : `/runs/${row.runId}`
}

const CHIP = 'inline-flex min-h-6 items-center gap-1.5 rounded-xs px-2 font-mono text-micro uppercase tracking-[0.04em]'

/**
 * §7.8 — the ruled sheet of recent decisions. The whole row opens the run; the question is the
 * button. Position + word, never a colour alone.
 */
export default function RecentWork({ rows }: { rows: RecentRow[] }) {
  return (
    <div className="mt-6 overflow-hidden rounded-lg bg-paper shadow-card">
      <div className="flex items-end justify-between gap-4 border-b border-hairline px-6 py-5">
        <div>
          <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Your decisions</p>
          <h2 className="font-display text-title font-medium tracking-[-0.02em] text-ink">Recent work</h2>
        </div>
        <Link to="/runs" className="font-ui text-body-sm text-accent underline underline-offset-4">
          View all
        </Link>
      </div>
      {rows.map((row) => (
        <article key={row.runId} className="border-t border-rule first:border-t-0">
          <Link
            to={rowTarget(row)}
            className="group flex flex-wrap items-center justify-between gap-3 px-6 py-4 hover:bg-accent-soft"
          >
            <span className="min-h-11 font-ui text-body-sm font-medium text-ink group-hover:text-accent group-hover:underline group-hover:underline-offset-4">
              {row.question}
            </span>
            <span className="flex flex-wrap items-center gap-4">
              {row.state === 'Filed' ? (
                <>
                  <span className={`${CHIP} bg-accent-soft text-ok`}>
                    <i className="h-1.5 w-1.5 rounded-full bg-ok" />Filed
                  </span>
                  {row.stance ? <PositionMark position={row.stance} size="sm" ground="light" /> : null}
                  <span className="font-mono text-micro text-ink-3">
                    {row.share === null ? '—' : row.share.toFixed(2)} &middot; {row.date}
                  </span>
                </>
              ) : row.state === 'Deliberating' ? (
                <>
                  <span className={`${CHIP} bg-sand text-warn`}>
                    <i className="h-1.5 w-1.5 rounded-full bg-warn" />Deliberating
                  </span>
                  <span className="font-mono text-micro text-ink-3">
                    pass {row.passes} &middot; {row.date}
                  </span>
                </>
              ) : (
                <>
                  <span className={`${CHIP} bg-sand ${row.state === 'Failed' ? 'text-danger' : 'text-warn'}`}>
                    <i className={`h-1.5 w-1.5 rounded-full ${row.state === 'Failed' ? 'bg-danger' : 'bg-warn'}`} />
                    {row.state}
                  </span>
                  <span className="font-mono text-micro text-ink-3">
                    pass {row.passes} &middot; {row.date}
                  </span>
                </>
              )}
            </span>
          </Link>
        </article>
      ))}
    </div>
  )
}
