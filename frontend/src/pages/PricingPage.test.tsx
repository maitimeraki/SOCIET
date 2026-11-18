import { afterEach, describe, expect, it, vi } from 'vitest'
// No jsdom / no testing-library in this repo: render to static markup in Node. MemoryRouter is
// required because the page's header and actions are `<Link>`s — React Router throws outside one.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { billingCheckout } from '../api/rest'
import PricingPage, {
  ENTERPRISE_ROWS,
  PLANS,
  defaultCountry,
  defaultCurrency,
  formatPrice,
  mergeServerPlans,
} from './PricingPage'
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
      { key: 'starter', prices: { INR: 900, USD: 12 }, price_label: null, units: 9000, max_agents: 12, max_rounds: 5 },
      { key: 'studio', prices: { INR: 1800, USD: 24 }, price_label: null, units: 18000, max_agents: 12, max_rounds: 6 },
      { key: 'enterprise', prices: { INR: null, USD: null }, price_label: 'Custom', units: 90000, max_agents: 12, max_rounds: 8 },
    ])

    expect(merged.plans[0]).toMatchObject({
      prices: { INR: 900, USD: 12 },
      rows: [
        ['Units / month', '9,000'],
        ['Panel size', '12'],
        ['Passes per decision', '5'],
      ],
    })
    expect(merged.plans[1].prices).toEqual({ INR: 1800, USD: 24 })
    expect(merged.enterprisePriceLabel).toBe('Custom')
    expect(merged.enterpriseRows).toEqual([
      ['Units / month', '90,000'],
      ['Panel size', '12'],
      ['Passes per decision', '8'],
    ])
  })

  it('shows the server seat cap in the static fallback, before the rate card loads', () => {
    for (const plan of PLANS) {
      expect(plan.rows).toContainEqual(['Panel size', '12'])
    }
    expect(ENTERPRISE_ROWS).toContainEqual(['Panel size', '12'])
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

describe('the currency', () => {
  it('keeps INR first in the fallback prices', () => {
    expect(PLANS[0].prices).toEqual({ INR: 999, USD: 10 })
    expect(PLANS[1].prices).toEqual({ INR: 1999, USD: 20 })
  })

  it('formats INR with ₹ and USD with $, and a missing price as a dash', () => {
    expect(formatPrice(1999, 'INR')).toBe('₹1,999')
    expect(formatPrice(10, 'USD')).toBe('$10')
    expect(formatPrice(null, 'INR')).toBe('—')
  })

  it('takes the billing country from the locale, falling back to the US', () => {
    expect(defaultCountry('en-IN')).toBe('IN')
    expect(defaultCountry('en-US')).toBe('US')
    expect(defaultCountry('en')).toBe('US')
    expect(defaultCountry(undefined)).toBe('US')
  })

  it('defaults the currency to INR only for India', () => {
    expect(defaultCurrency('IN')).toBe('INR')
    expect(defaultCurrency('US')).toBe('USD')
    expect(defaultCurrency('GB')).toBe('USD')
  })

  it('states the currencies in the enterprise footnote', () => {
    expect(render()).toContain('prices in INR or USD')
  })
})

describe('checkout', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('posts the plan with the chosen currency and country', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ url: 'https://pay.example/checkout' })))
    vi.stubGlobal('fetch', fetchMock)

    const { url } = await billingCheckout('studio', 'INR', 'IN')

    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toContain('/api/v1/billing/checkout')
    expect(JSON.parse(init.body as string)).toEqual({ plan: 'studio', currency: 'INR', country: 'IN' })
    expect(url).toBe('https://pay.example/checkout')
  })
})
