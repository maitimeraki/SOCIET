import { fmtDay, fmtInt } from '../../utils/format'

export interface StatsBandProps {
  plan: string
  unitsUsed: number
  unitsTotal: number
  unitsRemaining: number
  periodEnd: string
}

/**
 * §7.8 — one paper sheet divided by hairlines, not four floating cards. The first tile
 * carries the marked wash: this month's usage is the one thing the page is about. Every
 * figure comes from the server.
 */
export default function StatsBand(props: StatsBandProps) {
  const planLabel = props.plan.charAt(0).toUpperCase() + props.plan.slice(1)
  return (
    <div className="grid grid-cols-1 overflow-hidden rounded-lg bg-paper shadow-card sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1.2fr]">
      <div className="border-t border-hairline bg-[image:var(--gradient-marked)] p-5 sm:border-l-0 sm:border-t-0">
        <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Units used</p>
        <p className="tnum mt-2.5 font-mono text-[32px] leading-none tracking-[-0.04em] text-ink">{fmtInt(props.unitsUsed)}</p>
        <p className="mt-2 font-mono text-micro text-ink-3">of {fmtInt(props.unitsTotal)}</p>
      </div>
      <div className="border-t border-hairline p-5 sm:border-l sm:border-t-0">
        <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Units remaining</p>
        <p className="tnum mt-2.5 font-mono text-[32px] leading-none tracking-[-0.04em] text-ink">{fmtInt(props.unitsRemaining)}</p>
        <p className="mt-2 font-mono text-micro text-ink-3">left this period</p>
      </div>
      <div className="border-t border-hairline p-5 lg:border-l">
        <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Plan</p>
        <p className="tnum mt-2.5 font-mono text-[32px] leading-none tracking-[-0.04em] text-ink">{planLabel}</p>
      </div>
      <div className="border-t border-hairline p-5 lg:border-l">
        <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Resets</p>
        <p className="tnum mt-2.5 font-mono text-[32px] leading-none tracking-[-0.04em] text-ink">{fmtDay(props.periodEnd)}</p>
      </div>
    </div>
  )
}
