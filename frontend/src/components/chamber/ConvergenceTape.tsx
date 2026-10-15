import { STANCE_ORDER } from '../../run/selectors'
import type { TapeTick } from '../../run/selectors'
import type { Stance } from '../../run/events'
import { fmtPct } from '../../utils/format'

const SEGMENT_FILL: Record<Stance, string> = {
  POSITIVE: 'bg-stance-pos',
  NEUTRAL: 'bg-stance-neu',
  AMBIVALENT: 'bg-stance-amb',
  NEGATIVE: 'bg-stance-neg',
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
    <div className="rounded-[6px] border border-ink-4 bg-survey-paper-2 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-label uppercase text-ink-3">The Tape</h3>
        <span className="text-micro text-ink-3">weighted share per round vs {threshold.toFixed(2)}</span>
      </div>

      <div className="relative">
        {/* brass threshold line across all tracks — only meaningful once a tick exists */}
        {ticks.length > 0 && (
          <div aria-hidden="true" className="pointer-events-none absolute inset-y-0 z-10 w-px border-l-2 border-dashed border-brass" style={{ left: `calc(2.25rem + ${threshold} * (100% - 2.25rem))` }}>
            <span className="absolute -top-1 left-1.5 rounded-[4px] bg-survey-paper-2 px-1 font-measurement text-micro text-brass">{threshold.toFixed(2)}</span>
          </div>
        )}

        <div className="space-y-2">
          {ticks.length === 0 && <p className="text-body text-ink-3">Waiting for round 1…</p>}
          {ticks.map((tick) => (
            <div key={tick.round} className="flex items-center gap-3">
              <span className="tnum w-6 font-measurement text-micro text-ink-3">R{tick.round}</span>
              <div className="flex h-3 flex-1 overflow-hidden rounded-[4px]">
                {STANCE_ORDER.map((stance, index) => {
                  const share = tick.weights[stance] ?? 0
                  if (share <= 0) return null
                  return (
                    <div
                      key={stance}
                      title={`round ${tick.round} · ${stance} ${share.toFixed(2)}`}
                      className={`h-full ${SEGMENT_FILL[stance]} ${
                        index === 0 ? 'rounded-l-[4px]' : ''
                      } ${index === STANCE_ORDER.length - 1 ? 'rounded-r-[4px]' : ''} ${index > 0 ? 'ml-[2px]' : ''}`}
                      style={{ width: `calc(${share * 100}% - 2px)` }}
                    />
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </div>

      {active && (
        <p className="tnum mt-3 font-measurement text-mono text-ink-2">
          round {active.round}{active.dominant ? ` · ${active.dominant.stance} ${fmtPct(active.dominant.weightShare)} weighted share` : ''}
        </p>
      )}
    </div>
  )
}
