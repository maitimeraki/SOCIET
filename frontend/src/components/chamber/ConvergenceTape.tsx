import { STANCE_ORDER } from '../../run/selectors'
import type { TapeTick } from '../../run/selectors'
import type { Stance } from '../../run/events'
import StanceChip from '../common/StanceChip'
import { fmtPct } from '../../utils/format'

const SEGMENT_FILL: Record<Stance, string> = {
  POSITIVE: 'bg-pos-light',
  NEUTRAL: 'bg-neu-light',
  AMBIVALENT: 'bg-amb-light',
  NEGATIVE: 'bg-neg-light',
}

export default function ConvergenceTape({
  ticks,
  threshold,
  activeRound,
}: {
  ticks: TapeTick[]
  threshold: number
  activeRound: number | null
}) {
  const active = ticks.find((tick) => tick.round === (activeRound ?? ticks[ticks.length - 1]?.round))

  return (
    <div className="border-t border-ink-4 pt-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-label uppercase text-ink-3">The Tape</h3>
        <span className="text-micro text-ink-3">weighted share per pass vs {threshold.toFixed(2)}</span>
      </div>

      <div className="relative">
        {/* warn threshold line across all tracks — only meaningful once a tick exists */}
        {ticks.length > 0 && (
          <div aria-hidden="true" className="pointer-events-none absolute inset-y-0 z-10 w-px border-l-2 border-dashed border-warn" style={{ left: `calc(2.25rem + ${threshold} * (100% - 2.25rem))` }}>
            <span className="absolute -top-1 left-1.5 rounded-[4px] bg-ground-2 px-1 font-measurement text-micro text-ink-2">{threshold.toFixed(2)}</span>
          </div>
        )}

        <div className="space-y-2">
          {ticks.length === 0 && <p className="text-body text-ink-3">Waiting for pass 1…</p>}
          {ticks.map((tick) => {
            const present = STANCE_ORDER.filter((stance) => (tick.weights[stance] ?? 0) > 0)
            return (
              <div key={tick.round}>
                <div className="flex items-center gap-3">
                  <span className="tnum w-6 font-measurement text-micro text-ink-3">P{tick.round}</span>
                  <div className="flex h-3 flex-1 overflow-hidden rounded-[4px]" aria-hidden="true">
                    {STANCE_ORDER.map((stance, index) => {
                      const share = tick.weights[stance] ?? 0
                      if (share <= 0) return null
                      return (
                        <div
                          key={stance}
                          className={`h-full ${SEGMENT_FILL[stance]} ${
                            index === 0 ? 'rounded-l-[4px]' : ''
                          } ${index === STANCE_ORDER.length - 1 ? 'rounded-r-[4px]' : ''} ${index > 0 ? 'ml-[2px]' : ''}`}
                          style={{ width: `calc(${share * 100}% - 2px)` }}
                        />
                      )
                    })}
                  </div>
                </div>
                {/* §9 — colour is never the sole carrier: each stance present shows a symbol + word. */}
                <ul className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 pl-9">
                  {present.map((stance) => (
                    <li key={stance} className="flex items-center gap-1.5">
                      <StanceChip stance={stance} size="sm" />
                      <span className="tnum font-measurement text-micro text-ink-3">
                        {fmtPct(tick.weights[stance] ?? 0)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </div>
      </div>

      {active && (
        <p className="tnum mt-3 font-measurement text-mono text-ink-2">
          pass {active.round}{active.dominant ? ` · ${active.dominant.stance} ${fmtPct(active.dominant.weightShare)} weighted share` : ''}
        </p>
      )}
    </div>
  )
}
