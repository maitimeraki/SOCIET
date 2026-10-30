import { Link } from 'react-router-dom'
import PositionMark from '../ui/PositionMark'
import type { Position } from '../ui/PositionMark'

export interface RecentRow {
  runId: string
  question: string
  state: 'Filed' | 'Deliberating'
  stance: Position | null
  share: number | null
  passes: string
  date: string
}

/**
 * §7.8 — the ruled sheet of recent decisions. The question is the button; the whole row opens
 * the run. Position + word, never a colour alone.
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
        <article key={row.runId} className="flex flex-wrap items-center justify-between gap-3 border-t border-hairline px-6 py-4 first:border-t-0 hover:bg-accent-soft">
          <Link
            to={row.state === 'Deliberating' ? `/runs/${row.runId}` : `/results`}
            className="min-h-11 font-ui text-body-sm font-medium text-ink hover:text-accent hover:underline hover:underline-offset-4"
          >
            {row.question}
          </Link>
          <div className="flex flex-wrap items-center gap-4">
            {row.state === 'Filed' ? (
              <>
                <span className="inline-flex min-h-6 items-center gap-1.5 rounded-xs bg-accent-soft px-2 font-mono text-micro uppercase tracking-[0.04em] text-ok">
                  <i className="h-1.5 w-1.5 rounded-full bg-ok" />Filed
                </span>
                {row.stance ? <PositionMark position={row.stance} size="sm" ground="light" /> : null}
                <span className="font-mono text-micro text-ink-3">
                  {row.share === null ? '—' : row.share.toFixed(2)} &middot; {row.date}
                </span>
              </>
            ) : (
              <>
                <span className="inline-flex min-h-6 items-center gap-1.5 rounded-xs bg-sand px-2 font-mono text-micro uppercase tracking-[0.04em] text-warn">
                  <i className="h-1.5 w-1.5 rounded-full bg-warn" />Deliberating
                </span>
                <span className="font-mono text-micro text-ink-3">
                  pass {row.passes} &middot; {row.date}
                </span>
              </>
            )}
          </div>
        </article>
      ))}
    </div>
  )
}
