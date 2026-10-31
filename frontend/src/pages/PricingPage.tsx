import { Link } from 'react-router-dom'
import { buttonClasses } from '../components/ui/Button'

/**
 * §7.9 The rate card. Two metered units, two plans, one custom door, and the rules under the
 * plans. No calculator, no slider, no annual toggle, no urgency — the page's job is to make
 * the two units obvious and the custom path easy.
 *
 * The prices are placeholders pending unit economics: the hierarchy and the two units are the
 * design; the figures are not.
 */
const PLANS = [
  {
    name: 'Desk',
    for: 'For the first question.',
    amount: '$0',
    per: '/ month',
    rows: [
      ['Corpus', '250 MB / month'],
      ['Deep decisions', '3 / month'],
      ['The answer includes', 'Sources & case against'],
      ['Local-first', 'Included'],
    ],
    action: 'Start free',
    featured: false,
  },
  {
    name: 'Studio',
    for: 'For a standing practice.',
    amount: '$29',
    per: '/ month',
    rows: [
      ['Corpus', '2 GB / month'],
      ['Deep decisions', '20 / month'],
      ['The answer includes', 'Sources & case against'],
      ['Local-first', 'Included'],
    ],
    action: 'Start with Studio',
    featured: true,
  },
] as const

const RULES = [
  ['A document counts once.', 'Added to a corpus, read by the panel, re-read in a later decision: it counts once against that month.'],
  ['A deep decision counts once.', 'From the first pass to the filed answer. Reopening a filed answer does not count again.'],
  ['No seats.', 'One account, however many people read the verdict. The panel is the only metered thing.'],
] as const

export default function PricingPage() {
  return (
    <div className="min-h-[calc(100dvh-52px)] bg-bone">
      <header className="flex items-center justify-between gap-4 border-b border-hairline px-8 py-5">
        <Link to="/" className="flex items-center gap-2 text-ink">
          <span aria-hidden="true" className="font-display text-title leading-none">◆</span>
          <span className="font-ui text-[18px] font-semibold">Societas</span>
        </Link>
        <div className="flex items-center gap-3">
          <Link to="/overview" className="font-ui text-body-sm text-ink-2 underline underline-offset-4 hover:text-ink">
            Open the app
          </Link>
          <Link to="/auth/signup" className={buttonClasses('primary', 40, 'min-h-11')}>
            Start free
          </Link>
        </div>
      </header>

      <div className="mx-auto w-[min(1100px,calc(100%-48px))] py-[72px]">
        <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Plans</p>
        <h1 className="mt-3 max-w-[15ch] font-display text-display font-medium tracking-[-0.035em] text-ink">
          Pay for the material. And the arguments.
        </h1>
        <p className="mt-4 max-w-[56ch] font-ui text-body text-ink-2">
          Two things set every plan: how much your panel reads in a month, and how many deep decisions
          it argues. No seats. No per-question invoice.
        </p>

        <div className="mt-10 grid grid-cols-1 border-y border-rule sm:grid-cols-2">
          <div className="grid grid-cols-[36px_1fr] gap-4 py-[22px] sm:border-r sm:border-rule sm:pr-8">
            <span className="font-mono text-micro text-ink-3">01</span>
            <div>
              <strong className="block font-ui text-body-sm font-semibold text-ink">Corpus size</strong>
              <p className="mt-1 max-w-[44ch] font-ui text-body-sm text-ink-2">
                The source material your panel can hold and read in a month. A document counts once,
                however often it is read.
              </p>
            </div>
          </div>
          <div className="grid grid-cols-[36px_1fr] gap-4 border-t border-rule py-[22px] sm:border-t-0 sm:pl-8">
            <span className="font-mono text-micro text-ink-3">02</span>
            <div>
              <strong className="block font-ui text-body-sm font-semibold text-ink">Deep decisions</strong>
              <p className="mt-1 max-w-[44ch] font-ui text-body-sm text-ink-2">
                A question the panel argues to a filed answer. One decision counts once, however many
                passes it takes.
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto grid w-[min(1100px,calc(100%-48px))] grid-cols-1 gap-5 sm:grid-cols-[1fr_1.18fr]">
        {PLANS.map((plan) => (
          <article
            key={plan.name}
            className={`flex flex-col rounded-xl p-8 shadow-card ${plan.featured ? 'bg-[image:var(--gradient-marked)] shadow-sheet' : 'bg-paper'}`}
          >
            {plan.featured ? (
              <span className="mb-4 self-start rounded-full bg-accent px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.08em] text-on-accent">
                Most chosen
              </span>
            ) : null}
            <p className="font-ui text-label uppercase tracking-[0.1em] text-ink-3">{plan.name}</p>
            <p className="mt-1.5 font-ui text-body-sm text-ink-2">{plan.for}</p>
            <p className="my-6 flex items-baseline gap-2 border-b border-hairline pb-6">
              <span className="tnum font-mono text-[56px] leading-none tracking-[-0.05em] text-ink">{plan.amount}</span>
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
            <Link
              to="/auth/signup"
              className={buttonClasses(plan.featured ? 'primary' : 'secondary', 48, 'mt-auto min-h-11 w-full')}
            >
              {plan.action}
            </Link>
          </article>
        ))}
      </div>

      <section className="mx-auto mt-5 grid w-[min(1100px,calc(100%-48px))] grid-cols-1 items-center gap-10 rounded-xl bg-sand p-10 lg:grid-cols-[1.5fr_0.8fr]">
        <div>
          <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Custom</p>
          <h2 className="mt-2 max-w-[20ch] font-display text-heading font-medium tracking-[-0.025em] text-ink">
            A standing panel, or a corpus that keeps growing.
          </h2>
          <p className="mt-3 max-w-[52ch] font-ui text-body-sm text-ink-2">
            More than 2 GB a month, or the same panel against a living archive. Tell me the material
            and the question; I will propose the plan and the monthly price.
          </p>
        </div>
        <div className="grid justify-items-start gap-2.5">
          <a href="mailto:hello@societas.app?subject=Custom%20plan" className={buttonClasses('primary', 48, 'min-h-11')}>
            Talk to the founder
          </a>
          <p className="font-mono text-micro text-ink-3">Monthly billing &middot; cancel anytime &middot; prices in USD</p>
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

      <p className="mx-auto w-[min(1100px,calc(100%-48px))] border-t border-rule py-6 font-mono text-micro text-ink-3">
        Every plan runs on the machine you start it on.{' '}
        <Link to="/" className="text-accent underline underline-offset-4">
          Back to the product
        </Link>
      </p>
    </div>
  )
}
