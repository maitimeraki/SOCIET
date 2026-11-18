/* eslint-disable react-refresh/only-export-components -- the pure plan-action mapping is exported so the no-DOM suite can assert it without a renderer. */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, billingCancelSubscription, billingSubscription } from '../../api/rest'
import type { BillingSubscription } from '../../api/types'
import { inlineLinkClasses } from '../ui/Button'
import { fmtDay, fmtInt } from '../../utils/format'

export interface PlanUsageProps {
  plan: string
  unitsUsed: number
  unitsTotal: number
  unitsRemaining: number
  periodEnd: string
}

/** The statuses that still bill. Halted, cancelled and completed subscriptions do not. */
const LIVE_STATUSES = new Set(['active', 'pending', 'authenticated'])

export type PlanAction = 'cancel' | 'scheduled' | 'choose'

/** What the plan row offers: cancel a live plan, say that a cancelled one is still running, or choose a plan. */
export function planAction(subscription: BillingSubscription | null): PlanAction {
  if (subscription === null || !LIVE_STATUSES.has(subscription.status)) return 'choose'
  return subscription.cancel_at_period_end ? 'scheduled' : 'cancel'
}

const LINK_CLASSES = `${inlineLinkClasses} font-ui text-body-sm text-accent underline underline-offset-4`

/**
 * §7.8 — the only place a plan appears inside the app. Every figure is the server's
 * (`GET /api/v1/billing/usage`); the client never invents a limit. A meter over 90% turns
 * sienna, never red.
 */
export default function PlanUsage({ plan, unitsUsed, unitsTotal, unitsRemaining, periodEnd }: PlanUsageProps) {
  // `undefined` until the subscription read answers. Until then the action slot stays empty:
  // neither a cancel nor a plan choice is right for every account.
  const [subscription, setSubscription] = useState<BillingSubscription | null | undefined>(undefined)
  const [cancelling, setCancelling] = useState(false)
  const [planError, setPlanError] = useState<string | null>(null)
  const pct = unitsTotal > 0 ? Math.min(100, Math.round((unitsUsed / unitsTotal) * 100)) : 0
  const planLabel = plan.charAt(0).toUpperCase() + plan.slice(1)
  const action = subscription === undefined ? null : planAction(subscription)

  useEffect(() => {
    let active = true
    billingSubscription()
      .then((next) => {
        if (active) setSubscription(next)
      })
      .catch((error: unknown) => {
        if (active) setPlanError(error instanceof ApiError ? error.detail : "Couldn't load your plan. Try again.")
      })
    return () => {
      active = false
    }
  }, [])

  async function cancel() {
    setPlanError(null)
    setCancelling(true)
    try {
      setSubscription(await billingCancelSubscription())
    } catch (error) {
      setPlanError(error instanceof ApiError ? error.detail : "Couldn't cancel your plan. Try again.")
    } finally {
      setCancelling(false)
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
        {action === 'cancel' && (
          <button type="button" onClick={() => void cancel()} disabled={cancelling} className={LINK_CLASSES}>
            {cancelling ? 'Cancelling…' : 'Cancel plan'}
          </button>
        )}
        {action === 'choose' && (
          <Link to="/pricing" className={LINK_CLASSES}>
            Choose a plan
          </Link>
        )}
      </div>
      {action === 'scheduled' && (
        <p className="mt-2 font-ui text-micro text-ink-2">
          Your plan stays active until{' '}
          {subscription?.current_period_end ? fmtDay(subscription.current_period_end) : 'the end of this period'}.
        </p>
      )}
      {planError && (
        <p role="alert" className="mt-2 text-micro text-ink-2">
          {planError}
        </p>
      )}
    </section>
  )
}
