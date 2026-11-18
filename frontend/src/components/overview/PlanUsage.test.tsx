import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { BillingSubscription } from '../../api/types'
import PlanUsage, { planAction } from './PlanUsage'

const render = (over: Partial<Parameters<typeof PlanUsage>[0]> = {}) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <PlanUsage
        plan="studio"
        unitsUsed={3200}
        unitsTotal={5000}
        unitsRemaining={1800}
        periodEnd="2026-11-01T00:00:00Z"
        {...over}
      />
    </MemoryRouter>,
  )

const subscription = (over: Partial<BillingSubscription> = {}): BillingSubscription => ({
  status: 'active',
  plan: 'studio',
  currency: 'INR',
  current_period_end: '2026-12-01T00:00:00Z',
  cancel_at_period_end: false,
  ...over,
})

describe('the plan meter', () => {
  it('shows the passed plan, not a literal', () => {
    expect(render()).toContain('Studio')
    expect(render({ plan: 'starter' })).toContain('Starter')
  })

  it('meters the server figures', () => {
    const html = render()
    expect(html).toContain('Units used')
    expect(html).toContain('3,200')
    expect(html).toContain('of 5,000')
    expect(html).toContain('1,800 units remaining')
    expect(html).toContain('aria-valuenow="64"') // 3200 / 5000
    expect(html).toContain('Resets 1 Nov 2026')
  })

  it('shows no plan action until the subscription has loaded', () => {
    const html = render()
    expect(html).not.toContain('href="/pricing"')
    expect(html).not.toContain('Choose a plan')
    expect(html).not.toContain('Cancel plan')
  })
})

describe('the plan action', () => {
  it('offers a cancel for a live subscription that is not already ending', () => {
    expect(planAction(subscription())).toBe('cancel')
    expect(planAction(subscription({ status: 'pending' }))).toBe('cancel')
    expect(planAction(subscription({ status: 'authenticated' }))).toBe('cancel')
  })

  it('says the plan stays on until its end once the cancel is scheduled', () => {
    expect(planAction(subscription({ cancel_at_period_end: true }))).toBe('scheduled')
  })

  it('offers a plan choice when there is no live subscription', () => {
    expect(planAction(null)).toBe('choose')
    expect(planAction(subscription({ status: 'halted' }))).toBe('choose')
    expect(planAction(subscription({ status: 'cancelled' }))).toBe('choose')
    expect(planAction(subscription({ status: 'completed' }))).toBe('choose')
  })
})
