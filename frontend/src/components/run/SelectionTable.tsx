import { Fragment } from 'react'
import type { SelectionRow } from '../../run/events'
import { fmtScore } from '../../utils/format'

/** DebateConfig.selection_score_threshold default — display-only; not exposed in UI v1. */
export const SELECTION_THRESHOLD = 0.6

export default function SelectionTable({
  rows,
  threshold = SELECTION_THRESHOLD,
}: {
  rows: SelectionRow[]
  threshold?: number
}) {
  const sorted = [...rows].sort((a, b) => b.blended - a.blended)
  return (
    <div className="rounded-[6px] border border-ink-700 bg-ink-900 p-4">
      <div className="grid grid-cols-[1fr_auto_auto_minmax(180px,240px)] items-center gap-x-4 gap-y-2">
        <span className="text-label uppercase text-paper-mute">Name</span>
        <span className="text-label uppercase text-paper-mute">semantic</span>
        <span className="text-label uppercase text-paper-mute">density</span>
        <span className="text-label uppercase text-paper-mute">blended</span>
        {sorted.map((row) => (
          <Fragment key={row.name}>
            <span className="text-body text-paper">{row.name}</span>
            <span className="tnum font-mono text-mono text-paper-dim">{fmtScore(row.semantic)}</span>
            <span className="tnum font-mono text-mono text-paper-dim">{fmtScore(row.density)}</span>
            <span className="flex items-center gap-2">
              <span className="relative h-1.5 flex-1 rounded-[4px] bg-ink-700">
                <span
                  className="absolute inset-y-0 left-0 rounded-[4px] bg-accent"
                  style={{ width: `${Math.min(1, row.blended) * 100}%` }}
                />
                <span
                  className="absolute inset-y-[-3px] w-px bg-brass"
                  style={{ left: `${threshold * 100}%` }}
                  aria-hidden="true"
                />
              </span>
              <span className="tnum w-9 text-right font-mono text-mono text-paper">{fmtScore(row.blended)}</span>
            </span>
          </Fragment>
        ))}
      </div>
      <p className="mt-3 text-micro text-paper-mute">
        Ranked by blended semantic + density score (weights 0.6 / 0.4). Below {threshold.toFixed(2)} the society falls
        back to density alone.
      </p>
    </div>
  )
}
