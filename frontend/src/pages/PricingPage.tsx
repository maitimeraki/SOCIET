/* eslint-disable react-refresh/only-export-components -- the pure plan mapping is exported so the no-DOM suite can assert it without a renderer. */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, billingCheckout, billingPlans } from '../api/rest'
import type { BillingCurrency, BillingPlan } from '../api/types'
import { useAuthStore } from '../auth/authStore'
import { buttonClasses, inlineLinkClasses } from '../components/ui/Button'
import Input from '../components/ui/Input'
import Select from '../components/ui/Select'
import { LEGAL_LINKS } from '../config/legalLinks'

/**
 * §7.9 The rate card. One metered pool, two plans, one custom door, and the rules under the
 * plans. These constants are the initial/SSR fallback; once `/billing/plans` loads, the server's
 * values replace them — the client invents no limit.
 */
export interface PlanCard {
  key: 'starter' | 'studio'
  name: string
  for: string
  /** INR first. A currency the server has no price for is null and renders as a dash. */
  prices: Record<BillingCurrency, number | null>
  per: string
  rows: [string, string][]
  action: string
  featured: boolean
}

export const PLANS: PlanCard[] = [
  {
    key: 'starter',
    name: 'Starter',
    for: 'For the first questions.',
    prices: { INR: 999, USD: 10 },
    per: '/ month',
    rows: [
      ['Units / month', '8,000'],
      ['Panel size', '12'],
      ['Passes per decision', '4'],
    ],
    action: 'Start with Starter',
    featured: false,
  },
  {
    key: 'studio',
    name: 'Studio',
    for: 'For a standing practice.',
    prices: { INR: 1999, USD: 20 },
    per: '/ month',
    rows: [
      ['Units / month', '16,000'],
      ['Panel size', '12'],
      ['Passes per decision', '4'],
    ],
    action: 'Start with Studio',
    featured: true,
  },
]

export const ENTERPRISE_ROWS: [string, string][] = [
  ['Units / month', 'Custom'],
  ['Panel size', '12'],
  ['Passes per decision', '4'],
]

export const ENTERPRISE_PRICE_LABEL = 'Custom pricing'

const COUNTRY_CODE = /^[A-Z]{2}$/

export function planRows(plan: BillingPlan): [string, string][] {
  return [
    ['Units / month', plan.units.toLocaleString('en-US')],
    ['Panel size', String(plan.max_agents)],
    ['Passes per decision', String(plan.max_rounds)],
  ]
}

/** `₹999`, `$10`. A price the server does not have is a dash. */
export function formatPrice(amount: number | null, currency: BillingCurrency): string {
  if (amount === null) return '—'
  return `${currency === 'INR' ? '₹' : '$'}${amount.toLocaleString('en-US')}`
}

/** The browser's language tag; the static render has no navigator, so it reads as none. */
function browserLanguage(): string | undefined {
  return typeof navigator === 'undefined' ? undefined : navigator.language
}

/** The billing country from a locale tag, or the US when the tag carries no region. */
export function defaultCountry(language?: string): string {
  return (language ? new Intl.Locale(language).region : undefined) ?? 'US'
}

export function defaultCurrency(country: string): BillingCurrency {
  return country === 'IN' ? 'INR' : 'USD'
}

/** Map the server's rate card onto the fallback card layout (pure, so it is testable). */
export function mergeServerPlans(rows: BillingPlan[]): {
  plans: PlanCard[]
  enterprisePriceLabel: string
  enterpriseRows: [string, string][]
} {
  const byKey = new Map(rows.map((row) => [row.key, row]))
  const enterprise = byKey.get('enterprise')
  return {
    plans: PLANS.map((plan) => {
      const server = byKey.get(plan.key)
      return server ? { ...plan, prices: server.prices, rows: planRows(server) } : plan
    }),
    enterprisePriceLabel: enterprise?.price_label ?? ENTERPRISE_PRICE_LABEL,
    enterpriseRows: enterprise ? planRows(enterprise) : ENTERPRISE_ROWS,
  }
}

const RULES = [
  ['One pool.', 'A unit is spent when the panel reads your material or argues a pass.'],
  ['It resets each period.', 'The balance resets at the end of the billing period; nothing rolls over.'],
  ['No seats.', 'One account, however many people read the verdict.'],
] as const

export default function PricingPage() {
  const user = useAuthStore((s) => s.user)
  const [country, setCountry] = useState(() => defaultCountry(browserLanguage()))
  const [currency, setCurrency] = useState<BillingCurrency>(() => defaultCurrency(country))
  const [buying, setBuying] = useState<'starter' | 'studio' | null>(null)
  const [checkoutError, setCheckoutError] = useState<string | null>(null)
  const [plans, setPlans] = useState<PlanCard[]>(PLANS)
  const [enterprisePriceLabel, setEnterprisePriceLabel] = useState(ENTERPRISE_PRICE_LABEL)
  const [enterpriseRows, setEnterpriseRows] = useState<[string, string][]>(ENTERPRISE_ROWS)
  const countryValid = COUNTRY_CODE.test(country)

  useEffect(() => {
    let active = true
    billingPlans()
      .then((rows) => {
        if (!active) return
        const merged = mergeServerPlans(rows)
        setPlans(merged.plans)
        setEnterprisePriceLabel(merged.enterprisePriceLabel)
        setEnterpriseRows(merged.enterpriseRows)
      })
      .catch(() => {
        // The fallback is already rendered; a rate-card fetch failure must not break the page.
      })
    return () => {
      active = false
    }
  }, [])

  async function buy(plan: 'starter' | 'studio') {
    setCheckoutError(null)
    setBuying(plan)
    try {
      const { url } = await billingCheckout(plan, currency, country)
      window.location.assign(url)
    } catch (error) {
      setCheckoutError(error instanceof ApiError ? error.detail : "Checkout isn't available yet.")
      setBuying(null)
    }
  }

  return (
    <div className="min-h-[calc(100dvh-52px)] bg-bone">
      <header className="flex items-center justify-between gap-4 border-b border-hairline px-8 py-5">
        <Link to="/" className="flex items-center gap-2 text-ink">
          <span aria-hidden="true" className="font-display text-title leading-none">◆</span>
          <span className="font-ui text-[18px] font-semibold">Societas</span>
        </Link>
        <div className="flex items-center gap-3">
          <Link
            to="/overview"
            className={`${inlineLinkClasses} font-ui text-body-sm text-ink-2 underline underline-offset-4 hover:text-ink`}
          >
            Open the app
          </Link>
          <Link to="/auth/signup?next=/pricing" className={buttonClasses('primary', 40, 'min-h-11')}>
            Free to start · No card
          </Link>
        </div>
      </header>

      <div className="mx-auto w-[min(1100px,calc(100%-48px))] py-[72px]">
        <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Plans</p>
        <h1 className="mt-3 max-w-[15ch] font-display text-display font-medium tracking-[-0.035em] text-ink">
          Pay for the material. And the arguments.
        </h1>
        <p className="mt-4 max-w-[56ch] font-ui text-body text-ink-2">
          One unit pool per month, sized by how much material your panel reads and how many passes it
          argues. No seats. No per-question invoice.
        </p>

        <div className="mt-10 grid grid-cols-[36px_1fr] gap-4 border-y border-rule py-[22px]">
          <span className="font-mono text-micro text-ink-3">01</span>
          <div>
            <strong className="block font-ui text-body-sm font-semibold text-ink">One unit pool per month</strong>
            <p className="mt-1 max-w-[52ch] font-ui text-body-sm text-ink-2">
              A unit is spent when the panel reads your material or argues a pass. The balance resets at
              the end of the billing period. No per-question invoice. No seats.
            </p>
          </div>
        </div>
      </div>

      <div className="mx-auto flex w-[min(1100px,calc(100%-48px))] flex-wrap items-end gap-4">
        <label className="grid gap-1.5">
          <span className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Currency</span>
          <Select value={currency} onChange={(event) => setCurrency(event.target.value as BillingCurrency)}>
            <option value="INR">INR (₹)</option>
            <option value="USD">USD ($)</option>
          </Select>
        </label>
        <label className="grid w-28 gap-1.5">
          <span className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Billing country</span>
          <Input
            value={country}
            onChange={(event) => setCountry(event.target.value.toUpperCase().replace(/[^A-Z]/g, '').slice(0, 2))}
            maxLength={2}
            autoComplete="country"
            aria-invalid={!countryValid}
            className="font-mono uppercase"
          />
        </label>
        {!countryValid && (
          <p className="pb-3 font-mono text-micro text-ink-3">Use a two-letter country code, such as IN or US.</p>
        )}
      </div>

      <div className="mx-auto mt-6 grid w-[min(1100px,calc(100%-48px))] grid-cols-1 gap-5 sm:grid-cols-2">
        {plans.map((plan) => (
          <article
            key={plan.name}
            className={`flex flex-col rounded-xl p-8 shadow-card ${plan.featured ? 'bg-[image:var(--gradient-marked)] shadow-sheet' : 'bg-paper'}`}
          >
            <p className="font-ui text-label uppercase tracking-[0.1em] text-ink-3">{plan.name}</p>
            <p className="mt-1.5 font-ui text-body-sm text-ink-2">{plan.for}</p>
            <p className="my-6 flex items-baseline gap-2 border-b border-hairline pb-6">
              <span className="tnum font-mono text-[56px] leading-none tracking-[-0.05em] text-ink">
                {formatPrice(plan.prices[currency], currency)}
              </span>
              <span className="font-mono text-micro uppercase tracking-[0.06em] text-ink-3">{plan.per}</span>
            </p>
            <ul className="mb-8">
              {plan.rows.map(([label, value]) => (
                <li key={label} className="flex items-baseline justify-between gap-4 border-t border-hairline py-2.5 first:border-t-0">
                  <span className="font-ui text-body-sm text-ink-2">{label}</span>
                  <strong className="text-right font-mono text-mono font-medium text-ink">{value}</strong>
                </li>
              ))}
            </ul>
            {user ? (
              <button
                type="button"
                onClick={() => void buy(plan.key)}
                disabled={buying !== null || !countryValid}
                className={buttonClasses(plan.featured ? 'primary' : 'secondary', 48, 'mt-auto min-h-11 w-full')}
              >
                {buying === plan.key ? 'Opening checkout…' : plan.action}
              </button>
            ) : (
              <Link
                to="/auth/signup?next=/pricing"
                className={buttonClasses(plan.featured ? 'primary' : 'secondary', 48, 'mt-auto min-h-11 w-full')}
              >
                {plan.action}
              </Link>
            )}
          </article>
        ))}
      </div>

      {checkoutError && (
        <div role="alert" className="field-invalid mx-auto mt-4 w-[min(1100px,calc(100%-48px))] pl-3">
          <p className="text-body text-ink-2">{checkoutError}</p>
        </div>
      )}

      <section className="mx-auto mt-5 grid w-[min(1100px,calc(100%-48px))] grid-cols-1 items-center gap-10 rounded-xl bg-sand p-10 lg:grid-cols-[1.5fr_0.8fr]">
        <div>
          <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Custom</p>
          <h2 className="mt-2 max-w-[20ch] font-display text-heading font-medium tracking-[-0.025em] text-ink">
            Enterprise
          </h2>
          <p className="mt-2 font-mono text-mono uppercase tracking-[0.06em] text-ink-3">{enterprisePriceLabel}</p>
          <p className="mt-3 max-w-[52ch] font-ui text-body-sm text-ink-2">
            More than 16,000 units a month, or the same panel against material that keeps growing. Tell
            us the material and the question; we will propose the plan and the monthly price.
          </p>
          <ul className="mt-5 max-w-[36ch]">
            {enterpriseRows.map(([label, value]) => (
              <li key={label} className="flex items-baseline justify-between gap-4 border-t border-hairline py-2.5 first:border-t-0">
                <span className="font-ui text-body-sm text-ink-2">{label}</span>
                <strong className="text-right font-mono text-mono font-medium text-ink">{value}</strong>
              </li>
            ))}
          </ul>
        </div>
        <div className="grid justify-items-start gap-2.5">
          <a href="mailto:hello@societas.app?subject=Enterprise%20plan" className={buttonClasses('primary', 48, 'min-h-11')}>
            Talk to the founder
          </a>
          <p className="font-mono text-micro text-ink-3">Monthly billing &middot; cancel anytime &middot; prices in INR or USD</p>
        </div>
      </section>

      <section className="mx-auto w-[min(1100px,calc(100%-48px))] py-16">
        <h2 className="font-display text-title font-medium tracking-[-0.025em] text-ink">What counts.</h2>
        <div className="mt-4 grid grid-cols-1 gap-8 border-t border-rule pt-5 sm:grid-cols-3">
          {RULES.map(([title, body]) => (
            <div key={title}>
              <h3 className="font-ui text-body-sm font-semibold text-ink">{title}</h3>
              <p className="mt-1.5 max-w-[34ch] font-ui text-body-sm text-ink-2">{body}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="mx-auto flex w-[min(1100px,calc(100%-48px))] flex-wrap items-center gap-x-5 gap-y-2 border-t border-rule py-6 font-mono text-micro text-ink-3">
        <span>Your material stays yours — export or delete it anytime.</span>
        {LEGAL_LINKS.map((link) => (
          <Link key={link.href} to={link.href} className="text-accent underline underline-offset-4">
            {link.label}
          </Link>
        ))}
        <Link to="/" className="text-accent underline underline-offset-4">
          Back to the product
        </Link>
      </footer>
    </div>
  )
}
