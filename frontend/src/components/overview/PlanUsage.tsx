import { Link } from 'react-router-dom'
import { fmtBytes } from '../../utils/format'

export interface PlanUsageProps {
  corpusBytes: number
  corpusLimit: number
  decisionsUsed: number
  decisionsLimit: number
  renews: string
}

/**
 * §7.8 — the only place a plan appears inside the app. It links to `/pricing`; it does not
 * reproduce the plans. A meter over 90% turns sienna, never red.
 */
export default function PlanUsage({ corpusBytes, corpusLimit, decisionsUsed, decisionsLimit, renews }: PlanUsageProps) {
  const corpusPct = Math.min(100, Math.round((corpusBytes / corpusLimit) * 100))
  const decisionPct = Math.min(100, Math.round((decisionsUsed / decisionsLimit) * 100))
  const meter = (pct: number, label: string) => (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      className="mt-2 h-1.5 overflow-hidden rounded-full bg-sand"
    >
      <span className={`block h-full rounded-full ${pct > 90 ? 'bg-caution' : 'bg-accent'}`} style={{ width: `${pct}%` }} />
    </div>
  )
  return (
    <section className="rounded-lg bg-paper p-5 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">This month</p>
          <h2 className="font-display text-title font-medium tracking-[-0.02em] text-ink">Plan &amp; usage</h2>
        </div>
        <span className="inline-flex min-h-6 items-center gap-1.5 rounded-xs bg-accent-soft px-2 font-mono text-micro uppercase tracking-[0.04em] text-ok">
          <i className="h-1.5 w-1.5 rounded-full bg-ok" />Studio
        </span>
      </div>
      <div className="mt-4">
        <div className="flex justify-between gap-3 font-mono text-micro text-ink-3">
          <span>Corpus</span>
          <span>
            <strong className="font-medium text-ink">{fmtBytes(corpusBytes)}</strong> of {fmtBytes(corpusLimit)}
          </span>
        </div>
        {meter(corpusPct, 'Corpus used')}
      </div>
      <div className="mt-4">
        <div className="flex justify-between gap-3 font-mono text-micro text-ink-3">
          <span>Deep decisions</span>
          <span>
            <strong className="font-medium text-ink">{decisionsUsed}</strong> of {decisionsLimit}
          </span>
        </div>
        {meter(decisionPct, 'Deep decisions used')}
      </div>
      <div className="mt-4 flex items-center justify-between gap-3 border-t border-hairline pt-3 font-mono text-micro text-ink-3">
        <span>Renews {renews}</span>
        <Link to="/pricing" className="font-ui text-body-sm text-accent underline underline-offset-4">
          Manage plan
        </Link>
      </div>
    </section>
  )
}
