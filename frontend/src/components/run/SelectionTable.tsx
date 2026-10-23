import { Fragment } from 'react'
import type { SelectionRow } from '../../run/events'
import { fmtScore } from '../../utils/format'
import { ruleClasses } from '../ui/Rule'

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
  const label = 'text-micro text-ink-3 sm:hidden'
  return (
    <div className={`${ruleClasses('top')} pt-4`}>
      {/* The column heads are a table on a wide screen; at 390 each candidate is one record — the
          name, then its three figures, wrapped, never a row wider than the page (§14.5). */}
      <div className="hidden grid-cols-[1fr_auto_auto_minmax(180px,240px)] items-center gap-x-4 gap-y-2 sm:grid">
        <span className="text-label uppercase text-ink-3">Name</span>
        <span className="text-label uppercase text-ink-3">semantic</span>
        <span className="text-label uppercase text-ink-3">density</span>
        <span className="text-label uppercase text-ink-3">blended</span>
      </div>
      <div className="mt-2 space-y-3 sm:grid sm:grid-cols-[1fr_auto_auto_minmax(180px,240px)] sm:items-center sm:gap-x-4 sm:gap-y-2 sm:space-y-0">
        {sorted.map((row) => (
          <Fragment key={row.name}>
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 sm:contents">
              <span className="w-full text-body text-ink sm:w-auto">{row.name}</span>
              <span className="tnum font-measurement text-mono text-ink-2">
                <span className={`mr-1 ${label}`}>semantic</span>
                {fmtScore(row.semantic)}
              </span>
              <span className="tnum font-measurement text-mono text-ink-2">
                <span className={`mr-1 ${label}`}>density</span>
                {fmtScore(row.density)}
              </span>
              <span className="flex items-center gap-2">
                <span className="relative hidden h-1.5 flex-1 rounded-[4px] bg-ink-4 sm:block">
                  <span
                    className="absolute inset-y-0 left-0 rounded-[4px] bg-accent"
                    style={{ width: `${Math.min(1, row.blended) * 100}%` }}
                  />
                  <span
                    className="absolute inset-y-[-3px] w-px bg-warn"
                    style={{ left: `${threshold * 100}%` }}
                    aria-hidden="true"
                  />
                </span>
                <span className={label}>blended</span>
                <span className="tnum w-9 text-right font-measurement text-mono text-ink">{fmtScore(row.blended)}</span>
              </span>
            </div>
          </Fragment>
        ))}
      </div>
      <p className="mt-3 text-micro text-ink-3">
        Ranked by blended semantic + density score (weights 0.6 / 0.4). Below {threshold.toFixed(2)} the panel falls
        back to density alone.
      </p>
    </div>
  )
}
