import { Link } from 'react-router-dom'
import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import Band from '../components/ui/Band'
import { buttonClasses } from '../components/ui/Button'
import Disclosure from '../components/ui/Disclosure'
import FiledSheet from '../components/ui/FiledSheet'
import PositionMark from '../components/ui/PositionMark'
import type { Position } from '../components/ui/PositionMark'
import { ruleClasses } from '../components/ui/Rule'
import './hero.css'

/**
 * The homepage — the hero page, at `/`. This is the first thing a visitor sees, and it is the
 * whole page: the split hero, then the twelve parts of §13.3 of `docs/FRONTEND_PRODUCTION_PLAN.md`.
 *
 * It replaced the retired landing sheet (`LandingPage` and its family), which is the world's
 * old voice. The bands and the rules it is built from are the kit's (`components/ui/Band.tsx`,
 * `components/ui/Rule.tsx`), so any other surface can take the same named surfaces instead of
 * copying this page's CSS. The five named surfaces (`--color-page`, `--color-band`,
 * `--color-surface-sky`, `--color-surface-warm`, `--color-surface-plum`) are global tokens.
 *
 * The order of the page is the order a stranger decides in, and every band has one job:
 *
 *   NAV → HERO (the feeling, and the product running) → FACTS (what is true) → THE PROBLEM (the
 *   cost of the status quo) → HOW IT WORKS 01–04 (the mechanism, in the order it happens) →
 *   WHAT YOU GET BACK (the deliverable) → A CONVERSATION VS. A FILED DECISION (the difference) →
 *   WHERE IT EARNS ITS KEEP (four real decisions) → WHAT IT DOES AND DOES NOT (the limits) →
 *   THE FILED DECISION (the real capture) → GOOD QUESTIONS → THE CLOSE.
 *
 * Two rules this page holds to:
 *   · feeling before topic — the first line names what the visitor feels, and the use cases come
 *     after the mechanism, never before it;
 *   · nothing is claimed that the product does not do, and the one piece of authored material on
 *     the page (the panel's turns) is labelled a worked example.
 *
 * The copy lives inline here on purpose: the strings are the page's, and the page is the only
 * place they are rendered.
 */

const CAPTURES = {
  map: {
    src: '/captures/map-material.png',
    alt: 'The map on a running decision: the material and the experts drawn as entries and connections, with the legend and the pane’s counts.',
    width: 2274,
    height: 904,
  },
  answer: {
    src: '/captures/answer.png',
    alt: 'The filed answer on screen: the question the panel was asked, the answer it filed, and the reasoning behind it.',
    width: 1036,
    height: 1390,
  },
} as const

const WORDMARK = 'Societas'

/**
 * The reveal: a band rises 8px into place when it first enters the viewport. It never hides
 * content — a faded-out section is invisible in any capture that does not scroll — so the band
 * simply sits 8px low until it arrives.
 */
function useReveal<T extends HTMLElement>() {
  const ref = useRef<T | null>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced || typeof IntersectionObserver === 'undefined') {
      el.classList.add('is-revealed')
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          entry.target.classList.add('is-revealed')
          observer.unobserve(entry.target)
        }
      },
      { threshold: 0.06, rootMargin: '0px 0px -6% 0px' }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return ref
}

/** The authored mark — an ink diamond. No plum in the header: one plum object per viewport. */
function BrandMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true" className="shrink-0 text-ink">
      <path d="M12 1.5 22.5 12 12 22.5 1.5 12Z" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M12 6.5 17.5 12 12 17.5 6.5 12Z" fill="currentColor" />
    </svg>
  )
}

/** The nav — a floating card over the ground, the way the reference floats its own. */
function Nav() {
  return (
    <div className="shell pt-5">
      <header className="hero-nav flex items-center justify-between gap-6 px-[17px] py-[11px]">
        <Link to="/" className="flex items-center gap-2.5 text-ink" aria-label={WORDMARK}>
          <BrandMark />
          <span className="font-titling text-[18px] font-semibold tracking-[-0.01em]">{WORDMARK}</span>
        </Link>
        <nav aria-label="Sections" className="hidden items-center gap-6 md:flex">
          <a href="#how-it-works" className="font-titling text-body text-ink-2 transition-colors duration-state hover:text-ink">
            How it works
          </a>
          <a href="#answer" className="font-titling text-body text-ink-2 transition-colors duration-state hover:text-ink">
            The answer
          </a>
          <a href="#questions" className="font-titling text-body text-ink-2 transition-colors duration-state hover:text-ink">
            Questions
          </a>
        </nav>
        <div className="flex items-center gap-2">
          <Link to="/auth/signin" className={buttonClasses('ghost', 40)}>
            Sign in
          </Link>
          <Link to="/auth/signup?next=/new" className={buttonClasses('secondary', 40)}>
            Start free
          </Link>
        </div>
      </header>
    </div>
  )
}

/**
 * The noise — the product as it actually runs, in three layers: the map (a real capture), the
 * panel arguing on it, and the filed answer overlapping the corner.
 *
 * The turns are AUTHORED material, so the panel is labelled a worked example. They are the only
 * words on the page that are not the product's own copy, and they are labelled as such.
 *
 * They are also the SAME decision the real capture at the foot of the page shows — Ridgeline
 * Coffee, a second location on Mill Street, and the answer "no" — so the top of the page and the
 * bottom of the page tell one story rather than two.
 */
const TURNS: { position: Position; who: string; said: string }[] = [
  {
    position: 'NEGATIVE',
    who: 'Operations lead',
    said: 'The grease-trap upgrade at 214 Mill Street is not signed, and occupancy is conditional on it.',
  },
  {
    position: 'AMBIVALENT',
    who: 'Finance lead',
    said: 'The lease runs $4,200 a month, but the clock only starts at occupancy, not at signing.',
  },
  {
    position: 'NEUTRAL',
    who: 'Market analyst',
    said: 'The demand study covers the current district. It says nothing about Mill Street.',
  },
  {
    position: 'POSITIVE',
    who: 'Site analyst',
    said: 'Alder Lane’s signed lease shows one operator can hold two sites at once.',
  },
]

function NoisePanel() {
  return (
    <figure className="hero-noise">
      <div className="hero-noise__strip">
        <p className="font-measurement text-[11px] uppercase tracking-[0.16em] text-map-ink">
          The map, and the panel over it
        </p>
        <span className="hero-noise__chip">Worked example</span>
      </div>

      <div className="hero-noise__map mt-3">
        <img
          className="block w-full object-cover"
          style={{ aspectRatio: '2274 / 704', objectPosition: '50% 0%' }}
          data-capture="map"
          src={CAPTURES.map.src}
          alt={CAPTURES.map.alt}
          width={CAPTURES.map.width}
          height={CAPTURES.map.height}
        />
      </div>

      <div className="mt-4 px-5 pb-1">
        <p className="font-measurement text-[11px] uppercase tracking-[0.16em] text-map-ink-2">
          The panel, arguing
        </p>
      </div>

      {TURNS.map((turn) => (
        <div key={turn.who} className={`hero-noise__row ${ruleClasses('top', 'dark')}`}>
          <p className="flex items-center gap-2 font-measurement text-[10px] uppercase tracking-[0.14em]">
            <PositionMark position={turn.position} size="sm" ground="map" />
            <span className="text-map-ink-2">{turn.who}</span>
          </p>
          <p className="mt-1 font-titling text-[13px] leading-[20px] text-map-ink">{turn.said}</p>
        </div>
      ))}

      <p className="hero-noise__note px-5 pt-4 font-measurement text-[11px] leading-[17px] text-map-ink-2">
        The map while the panel argues. Every turn lands on it before the next pass reads it.
      </p>

      {/* The filed answer — the only white object inside the dark surface, breaking the frame. */}
      <div className="hero-verdict p-5">
        <div className="flex items-center justify-between gap-3">
          <p className="font-measurement text-mono uppercase tracking-[0.14em] text-ink-3">Filed</p>
          <p className="flex items-center gap-2 font-measurement text-[11px] uppercase tracking-[0.14em] text-ink">
            <PositionMark position="NEGATIVE" size="sm" ground="light" />
          </p>
        </div>
        <p className="mt-2 flex items-baseline gap-2">
          <span className="font-measurement text-[34px] leading-[38px] tnum text-ink">0.82</span>
          <span className="font-measurement text-[10px] uppercase tracking-[0.14em] text-ink-3">
            the weighted share
          </span>
        </p>
        <div className={`${ruleClasses('top')} mt-3 pt-3`}>
          <p className="font-measurement text-mono uppercase tracking-[0.14em] text-caution">
            The case against
          </p>
          <p className="mt-1 font-titling text-[13px] leading-[20px] text-ink-2">
            If the upgrade lands on time, the Mill Street economics hold.
          </p>
        </div>
      </div>
    </figure>
  )
}

/**
 * The hero. Type-led: an eyebrow, one identity line, a lead and a body, ONE action, and the
 * composed product on the other side. The text column and the noise column are set against each
 * other on purpose — one sentence against many fragments is the product's whole proposition.
 */
function HeroSection() {
  return (
    <Band tone="page" className="pt-16" aria-labelledby="demo-hero-headline">
      <div className="shell">
        <div className="grid gap-14 xl:grid-cols-[560px_minmax(0,1fr)] xl:items-start xl:gap-16">
          <div>
            <p className="enter font-measurement text-mono uppercase tracking-[0.18em] text-ink-3" style={{ animationDelay: '0ms' }}>
              A panel of experts
            </p>
            <h1
              id="demo-hero-headline"
              className="enter mt-5 max-w-[16ch] font-record text-[clamp(2.75rem,1.6rem+4.2vw,68px)] font-semibold leading-[1.02] tracking-[-0.02em] text-ink"
              style={{ animationDelay: '60ms' }}
            >
              A decision you <em className="font-normal italic">can&rsquo;t</em> look up.
            </h1>
            <p
              className="enter mt-6 max-w-[42ch] font-titling text-[19px] leading-[28px] text-ink"
              style={{ animationDelay: '120ms' }}
            >
              The decision turns on documents you already have. The argument is what is missing.
            </p>
            <p
              className="enter mt-4 max-w-[52ch] font-titling text-[17px] leading-[28px] text-ink-2"
              style={{ animationDelay: '150ms' }}
            >
              Societas reads that material, convenes a panel of experts drawn from it, and makes them
              argue the question in passes. What comes back is an answer with the confidence behind
              it, the case against it, and every source attached.
            </p>
            <div className="enter mt-8 flex flex-wrap items-center gap-4" style={{ animationDelay: '180ms' }}>
              <Link to="/auth/signup?next=/new" data-action="primary" className="hero-action">
                Start your first decision
              </Link>
              <a
                href="#answer"
                className="font-titling text-body text-ink-2 underline decoration-ink-3 underline-offset-4 transition-colors duration-state hover:text-ink hover:decoration-accent"
              >
                See what it files
              </a>
            </div>
            <p className="enter mt-8 font-measurement text-mono text-ink-3" style={{ animationDelay: '240ms' }}>
              Runs on the machine you start it on · Free to use · No card, no tier
            </p>
          </div>

          <div className="enter" style={{ animationDelay: '200ms' }}>
            <NoisePanel />
          </div>
        </div>
      </div>
    </Band>
  )
}

/**
 * The facts. The product has no customers, no logos and no benchmarks, so this band carries the
 * honest properties instead — it is the reference's logo strip, filled with what is true.
 */
function Facts() {
  const facts = [
    {
      label: 'Local-first',
      body: 'The documents, the map and every decision stay on the machine running the tool.',
    },
    {
      label: 'No card, no tier',
      body: 'The product is free to use. It states its cost once and invents nothing else.',
    },
    {
      label: 'The case against',
      body: 'The strongest argument against the answer is kept whole, beside the answer.',
    },
  ]

  return (
    <Band tone="band" dense aria-label="What is true of the product">
      <div className="shell">
        <ul className="grid gap-8 md:grid-cols-3 md:gap-10">
          {facts.map((fact) => (
            <li key={fact.label} className={`${ruleClasses('top')} pt-4`}>
              <p className="font-measurement text-mono uppercase tracking-[0.14em] text-ink-3">{fact.label}</p>
              <p className="mt-2 max-w-[42ch] font-titling text-[15px] leading-[24px] text-ink-2">{fact.body}</p>
            </li>
          ))}
        </ul>
      </div>
    </Band>
  )
}

/**
 * The problem. Warm is caution, and this is the one place the page names the cost of the status
 * quo — before any mechanism arrives to remove it.
 */
function Problem() {
  const ref = useReveal<HTMLDivElement>()
  const lines = [
    'Everyone you ask will have an opinion.',
    'Almost nobody has read everything you have read.',
    'The strongest objection arrives last, if at all.',
  ]

  return (
    <Band tone="warm" aria-labelledby="demo-problem-heading">
      <div ref={ref} className="shell reveal">
        <div className="grid gap-10 lg:grid-cols-[1fr_1fr] lg:gap-20">
          <div>
            <h2 id="demo-problem-heading" className="font-record text-[40px] font-semibold leading-[1.1] tracking-[-0.02em] text-ink">
              The argument is the thing you&rsquo;re missing.
            </h2>
            <p className="mt-4 max-w-[48ch] font-titling text-[15px] leading-[24px] text-ink-2">
              Everyone you ask will have an opinion. Almost nobody has read everything you have read,
              argued the sides against each other, and told you the strongest objection. So the
              decision stays yours — made on a hunch you cannot defend.
            </p>
          </div>

          <ul className="self-end">
            {lines.map((line) => (
              <li key={line} className={`${ruleClasses('top')} py-4 font-titling text-[17px] leading-[26px] text-ink`}>
                {line}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Band>
  )
}

/** The mechanism — four movements, in the product's own order. */
function HowItWorks() {
  const ref = useReveal<HTMLDivElement>()
  const steps = [
    {
      key: '01',
      title: 'Add the material',
      body: 'Drop in the documents the decision turns on. Each one is read, and the map of what you know grows in front of you.',
    },
    {
      key: '02',
      title: 'Ask the question',
      body: 'Write the decision in your own words. The whole decision runs on that sentence, kept in view.',
    },
    {
      key: '03',
      title: 'The panel argues',
      body: 'Experts drawn from that material are paired over what their documents share and argue in passes. Every turn lands on the map before the next pass reads it.',
    },
    {
      key: '04',
      title: 'The answer is filed',
      body: 'A position, the confidence behind it, the strongest case against it, who held which view, and every source.',
    },
  ]

  return (
    <Band tone="sky" id="how-it-works" aria-labelledby="demo-how-heading">
      <div ref={ref} className="shell reveal">
        <h2 id="demo-how-heading" className="font-record text-[40px] font-semibold leading-[1.1] tracking-[-0.02em] text-ink">
          How it works
        </h2>
        <p className="mt-3 max-w-[56ch] font-titling text-[15px] leading-[24px] text-ink-2">
          Four movements, always in the same order: add your material, ask the question, let the
          panel argue, file the answer.
        </p>

        <ol className="mt-10 grid gap-8 md:grid-cols-4 md:gap-10">
          {steps.map((step) => (
            <li key={step.key} className={`${ruleClasses('top')} pt-4`}>
              <p className="font-measurement text-mono text-ink-3">{step.key}</p>
              <h3 className="mt-3 font-titling text-title text-ink">{step.title}</h3>
              <p className="mt-2 max-w-[38ch] font-titling text-[15px] leading-[24px] text-ink-2">{step.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </Band>
  )
}

/**
 * The answer — the deliverable, in four objects. Plum is the answer's own surface, and the one
 * caution rule inside it is the case against.
 */
function TheAnswer() {
  const ref = useReveal<HTMLDivElement>()
  const items = [
    {
      label: 'A position',
      body: 'The weighted share of the panel — not a summary of a conversation.',
    },
    {
      label: 'A confidence figure',
      body: 'What that share rests on, stated as a number you can argue with.',
    },
    {
      label: 'The case against',
      body: 'Kept whole, in its own voice, next to the answer.',
      caution: true,
    },
    {
      label: 'The sources',
      body: 'Every claim traceable to the section of your material it was read from.',
    },
  ]

  return (
    <Band tone="plum" id="answer" aria-labelledby="demo-answer-heading">
      <div ref={ref} className="shell reveal">
        <h2 id="demo-answer-heading" className="font-record text-[40px] font-semibold leading-[1.1] tracking-[-0.02em] text-ink">
          What you get back
        </h2>
        <p className="mt-3 max-w-[56ch] font-titling text-[15px] leading-[24px] text-ink-2">
          Four objects, every time — and none of them is a chat you have to keep asking.
        </p>

        <ul className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {items.map((item) => (
            <li
              key={item.label}
              className={`rounded-lg bg-canvas p-6 shadow-raised ${item.caution ? 'border-l-[3px] border-caution' : ''}`}
            >
              <p
                className={`font-measurement text-mono uppercase tracking-[0.14em] ${
                  item.caution ? 'text-caution' : 'text-ink-3'
                }`}
              >
                {item.label}
              </p>
              <p className="mt-3 font-titling text-[14px] leading-[22px] text-ink-2">{item.body}</p>
            </li>
          ))}
        </ul>

        <p className="mt-8 max-w-[60ch] font-titling text-[15px] leading-[24px] text-ink">
          Not a transcript. A document you can read on screen and take away.
        </p>
      </div>
    </Band>
  )
}

/**
 * The difference — and it is DRAWN, not written. A table of claims about a chat assistant and
 * about Societas is a claim; a thread that ends in nothing beside a document that ends in a
 * verdict is the same claim, shown. The visitor sees the difference in one glance, which is the
 * only way a difference is ever really believed.
 *
 * The left side is a conversation with nothing at the end of it. The right side is a filed
 * decision: the question, the position, the weighted share, the case against, the sources.
 */
function ChatBubble({ from, children }: { from: 'you' | 'them'; children: ReactNode }) {
  return (
    <div className={from === 'you' ? 'flex justify-end' : 'flex justify-start'}>
      <p
        className={`max-w-[40ch] rounded-lg px-4 py-2.5 font-titling text-[13px] leading-[20px] ${
          from === 'you' ? 'bg-canvas text-ink shadow-raised' : 'bg-band text-ink-2'
        }`}
      >
        {children}
      </p>
    </div>
  )
}

/** The filed decision, as the customer receives it: a sheet, not a summary.
 *
 * The sheet is the kit's own `FiledSheet`, so the homepage, the auth page's right column and the
 * dashboard's "The last answer" are one composed document. This one is AUTHORED material about a
 * named other party, so it is labelled a worked example — house style rule 9. */
const FILED_DECISION = {
  question: 'Should Ridgeline Coffee open a second location on Mill Street this spring?',
  position: 'NEGATIVE' as const,
  share: 0.82,
  caseAgainst: 'If the grease-trap work lands on time, the Mill Street economics hold.',
  sources: 'Mill Street lease · economics · grease-trap certification · Alder Lane lease',
}

function Difference() {
  const ref = useReveal<HTMLDivElement>()

  return (
    <Band tone="band" aria-labelledby="demo-difference-heading">
      <div ref={ref} className="shell reveal">
        <h2 id="demo-difference-heading" className="font-record text-[40px] font-semibold leading-[1.1] tracking-[-0.02em] text-ink">
          Not a conversation. A filed decision.
        </h2>
        <p className="mt-3 max-w-[56ch] font-titling text-[15px] leading-[24px] text-ink-2">
          Two things can end the same session. Only one of them leaves you holding something.
        </p>

        <div className="mt-10 grid gap-10 lg:grid-cols-2 lg:gap-16">
          {/* The conversation — it goes on, and it ends with nothing. */}
          <div>
            <p className="font-measurement text-mono uppercase tracking-[0.14em] text-ink-3">
              A conversation
            </p>
            <div className="mt-4 space-y-2.5">
              <ChatBubble from="you">Should we open a second location?</ChatBubble>
              <ChatBubble from="them">
                It depends on the lease terms, local demand and the current market. There are several
                factors worth weighing here.
              </ChatBubble>
              <ChatBubble from="you">So what would you do?</ChatBubble>
              <ChatBubble from="them">
                Happy to go into more detail on any of them. Let me know which aspect matters most to
                you.
              </ChatBubble>
            </div>
            <p className="mt-5 font-measurement text-mono uppercase tracking-[0.14em] text-ink-3">
              ▸ 14 more messages · no answer · nothing to keep
            </p>
            <p className="mt-2 font-titling text-[15px] leading-[24px] text-ink-2">
              …and the decision is still yours, made from a summary.
            </p>
          </div>

          {/* The filed decision — it ends. */}
          <div>
            <p className="font-measurement text-mono uppercase tracking-[0.14em] text-ink-3">
              A filed decision
            </p>
            <div className="mt-4">
              <FiledSheet decision={FILED_DECISION} sample />
            </div>
            <p className="mt-5 font-measurement text-mono uppercase tracking-[0.14em] text-ink-3">
              One sheet · the answer, the share behind it, the case against, the sources
            </p>
            <p className="mt-2 font-titling text-[15px] leading-[24px] text-ink-2">
              …and it is on your desk, with everything that produced it.
            </p>
          </div>
        </div>

        <p className="mt-10 max-w-[60ch] font-record text-[22px] leading-[32px] text-ink">
          The difference is not the interface. It is what you are holding at the end.
        </p>
      </div>
    </Band>
  )
}

/**
 * Where it earns its keep. These are the reader's own words — the decision they came with — and
 * each one names what it replaces, which is the thing they would otherwise be doing.
 */
function UseCases() {
  const ref = useReveal<HTMLDivElement>()
  const cases = [
    {
      question: 'Should we expand into a new market?',
      body: 'The contracts, the market notes and the reports you already hold are read into one map, and the experts drawn from them argue it against each other — including against the expansion.',
      replaces: 'Replaces the go / no-go meeting',
    },
    {
      question: 'Which supplier should we sign?',
      body: 'Each claim a supplier makes is read against the material you already have, and the panel divides over what the terms actually say.',
      replaces: 'Replaces the comparison sheet',
    },
    {
      question: 'Should we build this?',
      body: 'Your roadmap, your support threads and your own notes decide it — not a feature list you wrote before you knew anything.',
      replaces: 'Replaces the roadmap argument',
    },
    {
      question: 'Is this price right?',
      body: 'Your cost sheets, your contracts and the terms you were handed are argued over what they say, and the answer is filed with the sources.',
      replaces: 'Replaces the hunch',
    },
  ]

  return (
    <Band tone="page" id="use-cases" aria-labelledby="demo-cases-heading">
      <div ref={ref} className="shell reveal">
        <div className="grid gap-8 lg:grid-cols-[380px_1fr] lg:gap-16">
          <div>
            <h2 id="demo-cases-heading" className="font-record text-[40px] font-semibold leading-[1.1] tracking-[-0.02em] text-ink">
              Where it earns its keep
            </h2>
            <p className="mt-4 max-w-[38ch] font-titling text-[15px] leading-[24px] text-ink-2">
              One product, one question: whether to move, and why. The answer comes back with the
              case against it and the sources each expert argued from.
            </p>
          </div>

          <ul className="grid gap-4 sm:grid-cols-2">
            {cases.map((item) => (
              <li key={item.question} className="rounded-lg bg-canvas p-6 shadow-raised">
                <h3 className="font-titling text-heading text-ink">{item.question}</h3>
                <p className="mt-2 font-titling text-[14px] leading-[22px] text-ink-2">{item.body}</p>
                <p className="mt-4 font-measurement text-mono uppercase tracking-[0.14em] text-ink-3">{item.replaces}</p>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Band>
  )
}

/** What it does, and what it does not. The absences are stated once, and plainly. */
function Limits() {
  const ref = useReveal<HTMLDivElement>()
  const does = [
    { label: 'It runs on your machine', body: 'The documents, the map and every decision stay on the machine running the tool.' },
    { label: 'Every claim has a source', body: 'Each answer names the material each expert argued from, traceable to the section it was read from.' },
    { label: 'Every decision is kept', body: 'A finished decision reopens and renders exactly as it ended, pass by pass.' },
  ]
  const doesNot = [
    { label: 'It cannot invent a panel', body: 'The experts are drawn only from what you add. With no documents there is no panel and no answer.' },
    { label: 'It does not guarantee the answer', body: 'Confidence is the weighted share behind the position. It measures the panel, not the truth; a split is filed as a split.' },
    { label: 'It does not keep the text from your provider', body: 'The text your experts read and write goes to the provider you configure. Point it at a provider on your own machine if it must not leave.' },
  ]

  return (
    <Band tone="band" aria-labelledby="demo-limits-heading">
      <div ref={ref} className="shell reveal">
        <h2 id="demo-limits-heading" className="font-record text-[40px] font-semibold leading-[1.1] tracking-[-0.02em] text-ink">
          What this tool does — and does not
        </h2>
        <p className="mt-3 max-w-[56ch] font-titling text-[15px] leading-[24px] text-ink-2">
          Three properties are built into how the product works, and three limits come with them.
          No badges, testimonials or certifications are shown, because none exist.
        </p>

        <div className="mt-10 grid gap-10 md:grid-cols-2 md:gap-16">
          <div>
            <h3 className="font-titling text-heading text-ink">What it does</h3>
            <ul className={`${ruleClasses('around')} mt-4`}>
              {does.map((line) => (
                <li key={line.label} className="py-4">
                  <p className="font-titling font-medium text-ink">{line.label}</p>
                  <p className="mt-1 max-w-[52ch] font-titling text-[14px] leading-[22px] text-ink-2">{line.body}</p>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="font-titling text-heading text-ink">What it does not do</h3>
            <ul className={`${ruleClasses('around')} mt-4`}>
              {doesNot.map((line) => (
                <li key={line.label} className="py-4">
                  <p className="font-titling font-medium text-ink">{line.label}</p>
                  <p className="mt-1 max-w-[52ch] font-titling text-[14px] leading-[22px] text-ink-2">{line.body}</p>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </Band>
  )
}

/**
 * The filed decision — the one dark surface on the page, and the second of the two real captures.
 * The capture is held in a frame the page designed, and the band is the map's own surface.
 */
function FiledAnswer() {
  const ref = useReveal<HTMLDivElement>()
  return (
    <Band tone="dark" aria-labelledby="demo-filed-heading">
      <div ref={ref} className="shell reveal">
        <div className="grid gap-12 lg:grid-cols-[1fr_440px] lg:items-center lg:gap-20">
          <div>
            <h2 id="demo-filed-heading" className="font-record text-[40px] font-semibold leading-[1.1] tracking-[-0.02em] text-map-ink">
              The answer is a document you can open again.
            </h2>
            <p className="mt-4 max-w-[46ch] font-titling text-[15px] leading-[24px] text-map-ink-2">
              Not a summary, and not a message that disappears. The question as it was asked, the
              answer, the confidence, the case against, the position each expert took and the
              sources each argued from — and every turn, in order.
            </p>
            <p className="mt-6 font-measurement text-mono uppercase tracking-[0.14em] text-map-ink-2">
              Reopen it and it renders exactly as it ended
            </p>
          </div>

          <figure>
            <img
              className="w-full rounded-lg shadow-panel"
              style={{ aspectRatio: '1036 / 1390', objectFit: 'cover', objectPosition: '50% 0%' }}
              data-capture="answer"
              src={CAPTURES.answer.src}
              alt={CAPTURES.answer.alt}
              width={CAPTURES.answer.width}
              height={CAPTURES.answer.height}
            />
            <figcaption className="mt-3 text-[12px] leading-[18px] text-map-ink-2">
              A filed decision: the question, the answer, and the reasoning behind it.
            </figcaption>
          </figure>
        </div>
      </div>
    </Band>
  )
}

/** The questions owners actually ask. */
function Questions() {
  const ref = useReveal<HTMLDivElement>()
  const items = [
    {
      q: 'What is Societas?',
      a: 'A local tool that reads the documents your experts would have read, maps what is in them, and convenes a panel of experts drawn from that material to argue one question to an answer.',
    },
    {
      q: 'Do I need my own documents?',
      a: 'Yes. The panel is built from your material: no documents, no panel. Add the documents the decision turns on to begin.',
    },
    {
      q: 'What happens when I start a decision?',
      a: 'Your question is read for what it is asking. Possible experts are weighed against your material; each selected one is written up with a position and a confidence; then the passes begin — experts are paired over what they share, argue, and every turn is written back to the map before the next pass reads it.',
    },
    {
      q: 'How is the answer decided?',
      a: 'Each expert’s view is weighted by its confidence and conviction, and the answer is the weighted share behind each position. If no position has a clear majority, the answer says so plainly: a split, not a verdict.',
    },
    {
      q: 'Can experts change their minds?',
      a: 'Yes, and you can watch it happen: later passes read what earlier passes wrote, and each expert’s final position is its last turn.',
    },
    {
      q: 'Where does my data live?',
      a: 'The documents, the map and every decision stay on the machine running the tool. The text your experts read and write goes to the provider you configure — point it at a provider on your own machine if you want it to stay home.',
    },
    {
      q: 'Which providers work?',
      a: 'The one you configure. The product is not tied to a single provider, and a local provider keeps the text on your machine.',
    },
    {
      q: 'How long does a decision take?',
      a: 'It runs while you watch, and progress is shown as it happens; the time depends on how much material you add and the provider you choose. Nothing is hidden until the end.',
    },
    {
      q: 'Can I see what happens inside?',
      a: 'That is the point of the tool: you can see why each expert was chosen, who argued with whom, what each one said, and the sources behind the answer.',
    },
    {
      q: 'What happens to finished decisions?',
      a: 'They are kept. Reopen one and it renders exactly as it ended, pass by pass, with its answer, opposing case, positions and sources — or take the document away.',
    },
  ]

  return (
    <Band tone="page" dense id="questions" aria-labelledby="demo-faq-heading">
      <div ref={ref} className="shell reveal">
        <div className="grid gap-10 lg:grid-cols-[360px_1fr] lg:gap-20">
          <div>
            <h2 id="demo-faq-heading" className="font-record text-[40px] font-semibold leading-[1.1] tracking-[-0.02em] text-ink">
              Good questions.
            </h2>
            <p className="mt-3 max-w-[38ch] font-titling text-[15px] leading-[24px] text-ink-2">
              The questions owners actually ask, answered from how the product behaves — no more, no
              less.
            </p>
          </div>

          <div className="hero-faq">
            {items.map((item, index) => (
              <Disclosure key={item.q} summary={item.q} defaultOpen={index === 0}>
                <p className="max-w-[68ch] font-titling text-[14px] leading-[22px] text-ink-2">{item.a}</p>
              </Disclosure>
            ))}
          </div>
        </div>
      </div>
    </Band>
  )
}

/** The close — one action, on the brand's own tint, with the hero's exact words. */
function Close() {
  const ref = useReveal<HTMLDivElement>()
  return (
    <Band tone="plum" aria-labelledby="demo-close-heading">
      <div ref={ref} className="shell reveal text-center">
        <h2 id="demo-close-heading" className="mx-auto max-w-[18ch] font-record text-[44px] font-semibold leading-[1.08] tracking-[-0.02em] text-ink">
          Bring a question you can&rsquo;t look up.
        </h2>
        <p className="mx-auto mt-4 max-w-[46ch] font-titling text-[15px] leading-[24px] text-ink-2">
          Your documents, a panel drawn from them, and an answer filed with the case against.
        </p>
        <div className="mt-8 flex justify-center">
          <Link to="/auth/signup?next=/new" data-action="primary" className="hero-action">
            Start your first decision
          </Link>
        </div>
        <p className="mt-6 font-measurement text-mono text-ink-3">Free to use · No card, no tier</p>
      </div>
    </Band>
  )
}

/** The footer — wordmark, the real actions, the edition line. */
function Footer() {
  return (
    // The page's last band. It keeps its own `<footer>` element — the signed-off page's footer is
    // part of its DOM — so the band vocabulary carries `as="footer"`.
    <Band as="footer" tone="band" dense>
      <div className="shell">
        <div
          className={`flex flex-wrap items-end justify-between gap-x-8 gap-y-6 ${ruleClasses('top')} pt-6`}
        >
          <div>
            <div className="flex items-center gap-2.5 text-ink">
              <BrandMark />
              <p className="font-titling text-title font-semibold text-ink">{WORDMARK}</p>
            </div>
            <p className="mt-1 font-measurement text-mono text-ink-3">Local-first · v0.0.0 · decision panel</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Link to="/auth/signup?next=/new" className={buttonClasses('secondary', 40)}>
              Start a decision
            </Link>
            <a href="mailto:hello@societas.example" className={buttonClasses('ghost', 40)}>
              Talk to us
            </a>
          </div>
        </div>
      </div>
    </Band>
  )
}

/**
 * The homepage, at `/`. The design was built and signed off as the review preview (`/demo-home`,
 * `marketing/HomeDemo.tsx`); this file is the transfer of it, and `/` renders it.
 */
export default function Hero() {
  return (
    <div className="hero-page min-h-screen bg-ground text-ink">
      <Nav />
      <HeroSection />
      <Facts />
      <Problem />
      <HowItWorks />
      <TheAnswer />
      <Difference />
      <UseCases />
      <Limits />
      <FiledAnswer />
      <Questions />
      <Close />
      <Footer />
    </div>
  )
}
