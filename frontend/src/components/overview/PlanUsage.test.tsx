import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import PlanUsage from './PlanUsage'

const render = (over: Partial<Parameters<typeof PlanUsage>[0]> = {}) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <PlanUsage
        plan="studio"
        unitsUsed={3200}
        unitsTotal={5000}
        unitsRemaining={1800}
        periodEnd="2026-11-01T00:00:00Z"
        billingEnabled={false}
        {...over}
      />
    </MemoryRouter>,
  )

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

  it('links to /pricing when billing is not open', () => {
    const html = render()
    expect(html).toContain('href="/pricing"')
    expect(html).toContain('Manage plan')
  })

  it('offers a portal action instead when billing is open', () => {
    const html = render({ billingEnabled: true })
    expect(html).not.toContain('href="/pricing"')
    expect(html).toMatch(/<button[^>]*>Manage plan<\/button>/)
  })
})
