import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, billingPortal } from '../../api/rest'
import { inlineLinkClasses } from '../ui/Button'
import { fmtDay, fmtInt } from '../../utils/format'

export interface PlanUsageProps {
  plan: string
  unitsUsed: number
  unitsTotal: number
  unitsRemaining: number
  periodEnd: string
  billingEnabled: boolean
}

/**
 * §7.8 — the only place a plan appears inside the app. Every figure is the server's
 * (`GET /api/v1/billing/usage`); the client never invents a limit. A meter over 90% turns
 * sienna, never red.
 */
export default function PlanUsage({
  plan,
  unitsUsed,
  unitsTotal,
  unitsRemaining,
  periodEnd,
  billingEnabled,
}: PlanUsageProps) {
  const [portalError, setPortalError] = useState<string | null>(null)
  const pct = unitsTotal > 0 ? Math.min(100, Math.round((unitsUsed / unitsTotal) * 100)) : 0
  const planLabel = plan.charAt(0).toUpperCase() + plan.slice(1)

  async function manage() {
    setPortalError(null)
    try {
      const { url } = await billingPortal()
      window.location.assign(url)
    } catch (error) {
      setPortalError(error instanceof ApiError ? error.detail : "Couldn't open billing. Try again.")
    }
  }

  return (
    <section className="rounded-lg bg-paper p-5 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">This month</p>
          <h2 className="font-display text-title font-medium tracking-[-0.02em] text-ink">Plan &amp; usage</h2>
        </div>
        <span className="inline-flex min-h-6 items-center gap-1.5 rounded-xs bg-accent-soft px-2 font-mono text-micro uppercase tracking-[0.04em] text-ok">
          <i className="h-1.5 w-1.5 rounded-full bg-ok" />{planLabel}
        </span>
      </div>
      <div className="mt-4">
        <div className="flex justify-between gap-3 font-mono text-micro text-ink-3">
          <span>Units used</span>
          <span>
            <strong className="font-medium text-ink">{fmtInt(unitsUsed)}</strong> of {fmtInt(unitsTotal)}
          </span>
        </div>
        <div
          role="progressbar"
          aria-label="Units used"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          className="mt-2 h-1.5 overflow-hidden rounded-full bg-sand"
        >
          <span className={`block h-full rounded-full ${pct > 90 ? 'bg-caution' : 'bg-accent'}`} style={{ width: `${pct}%` }} />
        </div>
      </div>
      <p className="mt-3 font-mono text-micro text-ink-3">{fmtInt(unitsRemaining)} units remaining</p>
      <div className="mt-4 flex items-center justify-between gap-3 border-t border-hairline pt-3 font-mono text-micro text-ink-3">
        <span>Resets {fmtDay(periodEnd)}</span>
        {billingEnabled ? (
          <button
            type="button"
            onClick={() => void manage()}
            className={`${inlineLinkClasses} font-ui text-body-sm text-accent underline underline-offset-4`}
          >
            Manage plan
          </button>
        ) : (
          <Link to="/pricing" className={`${inlineLinkClasses} font-ui text-body-sm text-accent underline underline-offset-4`}>
            Manage plan
          </Link>
        )}
      </div>
      {portalError && (
        <p role="alert" className="mt-2 text-micro text-ink-2">
          {portalError}
        </p>
      )}
    </section>
  )
}
