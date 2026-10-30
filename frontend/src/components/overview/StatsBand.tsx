import { fmtBytes } from '../../utils/format'

export interface StatsBandProps {
  decisions: number
  filed: number
  corpusBytes: number
  corpusLimit: number
  decisionsLeft: number
  decisionsLimit: number
}

/**
 * §7.8 — one paper sheet divided by hairlines, not four floating cards. The first tile
 * carries the marked wash: this month's work is the one thing the page is about.
 */
export default function StatsBand(props: StatsBandProps) {
  return (
    <div className="grid grid-cols-1 overflow-hidden rounded-lg bg-paper shadow-card sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1.2fr]">
      <div className="border-t border-hairline bg-[image:var(--gradient-marked)] p-5 sm:border-l-0 sm:border-t-0">
        <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Decisions this month</p>
        <p className="tnum mt-2.5 font-mono text-[32px] leading-none tracking-[-0.04em] text-ink">{props.decisions}</p>
        <p className="mt-2 font-mono text-micro text-ink-3">one filed overnight</p>
      </div>
      <div className="border-t border-hairline p-5 sm:border-l sm:border-t-0">
        <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Filed</p>
        <p className="tnum mt-2.5 font-mono text-[32px] leading-none tracking-[-0.04em] text-ink">{props.filed}</p>
        <p className="mt-2 font-mono text-micro text-ink-3">ready to read</p>
      </div>
      <div className="border-t border-hairline p-5 lg:border-l">
        <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Corpus read</p>
        <p className="tnum mt-2.5 font-mono text-[32px] leading-none tracking-[-0.04em] text-ink">{fmtBytes(props.corpusBytes)}</p>
        <p className="mt-2 font-mono text-micro text-ink-3">of {fmtBytes(props.corpusLimit)} on Studio</p>
      </div>
      <div className="border-t border-hairline p-5 lg:border-l">
        <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Deep decisions left</p>
        <p className="tnum mt-2.5 font-mono text-[32px] leading-none tracking-[-0.04em] text-ink">{props.decisionsLeft}</p>
        <p className="mt-2 font-mono text-micro text-ink-3">of {props.decisionsLimit} this month</p>
      </div>
    </div>
  )
}
