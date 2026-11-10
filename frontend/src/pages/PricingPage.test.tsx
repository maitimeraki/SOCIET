import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo: render to static markup in Node. MemoryRouter is
// required because the page's header and actions are `<Link>`s — React Router throws outside one.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import PricingPage, { mergeServerPlans } from './PricingPage'
import { BANNED_TERMS, renderedText } from '../test/copyLaw'

const render = () =>
  renderToStaticMarkup(
    <MemoryRouter>
      <PricingPage />
    </MemoryRouter>,
  )

describe('the plans', () => {
  it('names the three plan lines, with no popularity claim', () => {
    const html = render()
    expect(html).toContain('Starter')
    expect(html).toContain('Studio')
    expect(html).toContain('Enterprise')
    expect(html).not.toContain('Desk')
    expect(html).not.toContain('Most chosen')
  })

  it('states units per month, panel size and passes per decision — and no material volume', () => {
    const html = render()
    expect(html).toContain('Units / month')
    expect(html).toContain('8,000')
    expect(html).toContain('16,000')
    expect(html).toContain('Panel size')
    expect(html).toContain('Passes per decision')
    expect(html).not.toContain('MB')
    expect(html).not.toContain('GB')
    expect(html).not.toMatch(/corpus/i)
    expect(html).not.toContain('decision / month')
    expect(html).not.toContain('Local-first')
  })

  it('renders no banned word', () => {
    expect(renderedText(render())).not.toMatch(BANNED_TERMS)
  })

  it('reaches all four legal documents from the footer', () => {
    const html = render()
    for (const href of ['/privacy', '/terms', '/refund', '/legal/subprocessors']) {
      expect(html).toContain(`href="${href}"`)
    }
    expect(html).toContain('Privacy')
    expect(html).toContain('Terms')
    expect(html).toContain('Refund')
    expect(html).toContain('Subprocessors')
  })

  it("renders the server's rate card when it loads", () => {
    const merged = mergeServerPlans([
      { key: 'starter', price_usd: 12, price_label: '$12', units: 9000, max_agents: 24, max_rounds: 5 },
      { key: 'studio', price_usd: 24, price_label: '$24', units: 18000, max_agents: 26, max_rounds: 6 },
      { key: 'enterprise', price_usd: null, price_label: 'Custom', units: 90000, max_agents: 48, max_rounds: 8 },
    ])

    expect(merged.plans[0]).toMatchObject({
      amount: '$12',
      rows: [
        ['Units / month', '9,000'],
        ['Panel size', '24'],
        ['Passes per decision', '5'],
      ],
    })
    expect(merged.plans[1].amount).toBe('$24')
    expect(merged.enterpriseRows).toEqual([
      ['Units / month', '90,000'],
      ['Panel size', '48'],
      ['Passes per decision', '8'],
    ])
  })

  it('keeps the enterprise mailto and the 44px targets', () => {
    const html = render()
    const open = [...html.matchAll(/<a\b[^>]*>/g)].map((match) => match[0]).find((tag) => tag.includes('href="/overview"'))
    expect(open).toContain('min-h-11')
    expect(html).toContain('mailto:hello@societas.app?subject=Enterprise%20plan')
    expect(html).not.toContain('societas.example')
    // Anonymous visitors get the signup door, never a checkout control.
    expect(html).toContain('href="/auth/signup?next=/pricing"')
  })
})
