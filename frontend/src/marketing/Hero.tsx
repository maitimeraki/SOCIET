import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'
import Band from '../components/ui/Band'
import { buttonClasses } from '../components/ui/Button'
import Disclosure from '../components/ui/Disclosure'
import FiledSheet from '../components/ui/FiledSheet'
import PositionMark from '../components/ui/PositionMark'
import { ruleClasses } from '../components/ui/Rule'
import './hero.css'

/**
 * The homepage — the Quiet Room marketing page, at `/`.
 *
 * The page is §7.1's twelve parts, in order, on alternating grounds:
 *
 *   NAV → HERO (5/7: the promise left, the evidence desk right) → FACTS (the ruled strip) →
 *   PROBLEM (sand) → HOW IT WORKS (four movements) → DIFFERENCE (5/7, the conversation faded) →
 *   WHAT YOU GET (the verdict sheet and four callouts) → WHY YOU CAN CHECK IT (sticky heading,
 *   four proof rows) → LIMITS (what it does, what it does not) → USE CASES (four ruled rows) →
 *   QUESTIONS (native details) → PINE CLOSE → FOOTER.
 *
 * Three laws hold the page: the bands alternate bone and sand and the pine close is the only dark
 * one; the first viewport carries exactly one evergreen object, the hero action; and nothing is
 * claimed that the product does not do. The one authored decision (Ridgeline Coffee) is labelled
 * a worked example everywhere it appears. The copy is inline because the page is its only owner.
 */

const CAPTURES = {
  map: {
    src: '/captures/map-material.png',
    alt: 'The map on a running decision: the material and the experts drawn as entries and connections, with the legend and the pane’s counts.',
    width: 2274,
    height: 904,
  },
} as const

const WORDMARK = 'Societas'

const EYEBROW = 'font-ui text-label uppercase text-ink-3'
const EYEBROW_MAP = 'font-ui text-label uppercase text-map-ink-2'
const H2 = 'font-display text-display text-ink'

/** The authored mark — an ink diamond. No plum in the header: one evergreen object per viewport. */
function BrandMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true" className="shrink-0 text-ink">
      <path d="M12 1.5 22.5 12 12 22.5 1.5 12Z" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M12 6.5 17.5 12 12 17.5 6.5 12Z" fill="currentColor" />
    </svg>
  )
}

function Eyebrow({ children, dark = false }: { children: ReactNode; dark?: boolean }) {
  return <p className={dark ? EYEBROW_MAP : EYEBROW}>{children}</p>
}

const SECTION_LINKS = [
  { href: '#how-it-works', label: 'How it works' },
  { href: '#answer', label: 'The answer' },
  { href: '#questions', label: 'Questions' },
]

/** The nav — a 72px bone bar over one hairline, not a floating card. */
function Nav() {
  return (
    <header className="sticky top-0 z-40 border-b border-rule bg-bone">
      <div className="shell flex h-[72px] items-center justify-between gap-6">
        <Link to="/" className="inline-flex min-h-11 items-center gap-2.5 text-ink" aria-label={WORDMARK}>
          <BrandMark />
          <span className="font-ui text-[18px] font-semibold tracking-[-0.01em]">{WORDMARK}</span>
        </Link>

        <nav aria-label="Sections" className="hidden items-center gap-7 min-[860px]:flex">
          {SECTION_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="font-ui text-body-sm text-ink-2 transition-colors duration-state hover:text-ink"
            >
              {link.label}
            </a>
          ))}
        </nav>

        <div className="hidden items-center gap-2 min-[860px]:flex">
          <Link to="/auth/signin" className={buttonClasses('ghost', 40)}>
            Sign in
          </Link>
          {/* Secondary, not primary: the hero owns the first viewport's one evergreen object. */}
          <Link to="/auth/signup?next=/new" className={buttonClasses('secondary', 40)}>
            Start free
          </Link>
        </div>

        <details className="relative min-[860px]:hidden">
          <summary className="flex min-h-11 cursor-pointer list-none items-center rounded-md border border-rule px-3 font-ui text-body-sm font-semibold text-ink [&::-webkit-details-marker]:hidden">
            Menu
          </summary>
          <div className="absolute right-0 top-[calc(100%+10px)] grid w-56 gap-1 rounded-md border border-rule bg-bone p-2">
            {SECTION_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="flex min-h-11 items-center rounded-sm px-3 font-ui text-body-sm text-ink-2 hover:bg-sand hover:text-ink"
              >
                {link.label}
              </a>
            ))}
            <Link
              to="/auth/signin"
              className="flex min-h-11 items-center rounded-sm px-3 font-ui text-body-sm text-ink-2 hover:bg-sand hover:text-ink"
            >
              Sign in
            </Link>
            <Link to="/auth/signup?next=/new" className={buttonClasses('secondary', 40, 'mt-1 w-full')}>
              Start free
            </Link>
          </div>
        </details>
      </div>
    </header>
  )
}

/**
 * The evidence desk — one composed object, not three cards. A dark map fragment with one live turn
 * above a filed sheet that overlaps the map's lower-right corner. On a phone the map is dropped and
 * the desk crops to the filed sheet (§10.2).
 *
 * The turn and the decision are AUTHORED material about a named other party, so the desk is
 * labelled a worked example (house style rule 9). It is the same Ridgeline Coffee decision the
 * difference section shows, so the page tells one story rather than three.
 */
const FILED_DECISION = {
  question: 'Should Ridgeline Coffee open a second location on Mill Street this spring?',
  position: 'NEGATIVE' as const,
  share: 0.82,
  caseAgainst: 'If the grease-trap work lands on time, the Mill Street economics hold.',
  sources: 'Mill Street lease · economics · grease-trap certification · Alder Lane lease',
}

const LIVE_TURN = {
  position: 'NEGATIVE' as const,
  who: 'Operations lead',
  said: 'The grease-trap upgrade at 214 Mill Street is not signed, and occupancy is conditional on it.',
}

function EvidenceDesk() {
  return (
    <figure aria-label="A worked example of a decision in progress">
      <div className="rounded-xl bg-[image:var(--gradient-map)] p-5 text-map-ink shadow-map max-[479px]:hidden">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="flex flex-wrap items-center gap-2 font-ui text-label uppercase text-map-ink-2">
            The map · live
            <span className="rounded-xs border border-map-rule px-2 py-0.5 font-mono text-[10px] font-normal tracking-[0.14em] text-map-ink-2">
              Worked example
            </span>
          </p>
          <p className="tnum font-mono text-micro text-map-ink-2">18 entries · 6 experts · 12 opinions</p>
        </div>

        <div className="mt-3 overflow-hidden rounded-md bg-map-ground-2">
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

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-micro text-map-ink-2">
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-corpus" aria-hidden="true" />
            Material
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-expert" aria-hidden="true" />
            Experts
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full" style={{ background: 'var(--color-neg)' }} aria-hidden="true" />
            Opinions
          </span>
          <span className="inline-flex items-center gap-1.5 text-map-accent">
            <span className="hero-live-dot size-2 rounded-full bg-map-accent" aria-hidden="true" />
            Live
          </span>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[5fr_7fr] lg:items-start">
        <div className="hidden rounded-lg bg-paper p-5 shadow-card min-[480px]:block">
          <p className="font-ui text-label uppercase text-ink-3">The panel · arguing</p>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <PositionMark position={LIVE_TURN.position} size="sm" ground="light" />
            <span className="font-mono text-micro text-ink-3">{LIVE_TURN.who}</span>
          </div>
          <p className="mt-2 font-display text-[19px] leading-[27px] tracking-[-0.01em] text-ink">
            “{LIVE_TURN.said}”
          </p>
          <p className={`${ruleClasses('top', 'hair')} mt-3 pt-2 font-mono text-micro text-ink-3`}>
            Pass 2 of 4 · filed to the map
          </p>
        </div>

        {/* On desktop the sheet breaks the map's lower-right corner. */}
        <div className="min-w-0 lg:-mt-20">
          <FiledSheet decision={FILED_DECISION} sample />
        </div>
      </div>
    </figure>
  )
}

/** The hero — a 5/7 split: the promise on the left, the product already working on the right. */
function HeroSection() {
  return (
    <Band tone="page" className="hero-first-light" aria-labelledby="hero-headline">
      <div className="shell">
        <div className="grid items-start gap-14 md:grid-cols-2 lg:grid-cols-[5fr_7fr] lg:gap-16">
          <div>
            <Eyebrow>A panel of experts</Eyebrow>
            <h1 id="hero-headline" className="mt-5 max-w-[16ch] font-display text-hero text-ink">
              The decision you can’t look up.
            </h1>
            <p className="mt-5 max-w-[46ch] font-ui text-subhead text-ink-2">
              The decision turns on documents you already have. The argument is what is missing.
            </p>
            <p className="mt-4 max-w-[52ch] font-ui text-body text-ink-2">
              Societas reads that material, convenes a panel of experts drawn from it, and makes them
              argue the question in passes. What comes back is an answer with the confidence behind it,
              the case against it, and every source attached.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-6">
              <Link to="/auth/signup?next=/new" data-action="primary" className={buttonClasses('primary', 48)}>
                Start your first decision
              </Link>
              <a
                href="#difference"
                className="inline-flex min-h-11 items-center font-ui text-body text-ink-2 underline decoration-rule underline-offset-[3px] transition-colors duration-state hover:text-ink hover:decoration-accent"
              >
                See what it files
              </a>
            </div>
            <p className="mt-5 font-mono text-micro text-ink-3">
              Free to start · No card · Runs on the machine you start it on
            </p>
          </div>

          <div className="min-w-0">
            <EvidenceDesk />
          </div>
        </div>
      </div>
    </Band>
  )
}

/** The facts strip — the reference's logo wall, filled with what is true instead. */
function Facts() {
  const facts = [
    {
      label: 'Local-first',
      body: 'The documents, the map and every decision stay on the machine you start the tool on.',
    },
    {
      label: 'Free to start · No card',
      body: 'The first decisions are free. A plan appears only when the material or the number of decisions outgrows the free tier.',
    },
    {
      label: 'The case against',
      body: 'The strongest argument against the answer is kept whole, beside the answer.',
    },
  ]

  return (
    <section aria-label="What is true of the product" className={`${ruleClasses('both')} bg-bone`}>
      <div className="shell py-8">
        <ul className="grid gap-6 md:grid-cols-3 md:gap-10">
          {facts.map((fact) => (
            <li key={fact.label} className={`${ruleClasses('top')} pt-4`}>
              <p className="font-ui text-label uppercase text-ink-3">{fact.label}</p>
              <p className="mt-2 max-w-[38ch] font-ui text-body-sm text-ink-2">{fact.body}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

/** The problem — stated as loss, on the page's one sand caution band. */
function Problem() {
  const lines = [
    'Everyone you ask will have an opinion.',
    'Almost nobody has read everything you have read.',
    'The strongest objection arrives last, if at all.',
  ]

  return (
    <Band tone="band" aria-labelledby="problem-heading">
      <div className="shell">
        <div className="grid gap-10 lg:grid-cols-[5fr_7fr] lg:gap-16">
          <div>
            <Eyebrow>The problem</Eyebrow>
            <h2 id="problem-heading" className={`${H2} mt-3`}>
              The argument is the thing you’re missing.
            </h2>
          </div>

          <div>
            <ul>
              {lines.map((line) => (
                <li key={line} className={`${ruleClasses('top')} py-5 font-ui text-subhead text-ink`}>
                  {line}
                </li>
              ))}
            </ul>
            <p className="mt-4 max-w-[48ch] font-ui text-body-sm text-ink-2">
              So the decision stays yours — made on a hunch you cannot defend.
            </p>
          </div>
        </div>
      </div>
    </Band>
  )
}

/** The mechanism — four movements, a horizontal timeline on desktop and a vertical list on phone. */
function HowItWorks() {
  const steps = [
    {
      num: '01',
      title: 'Add the material.',
      body: 'Drop in the documents the decision turns on. Each one is read, and the map of what you know grows in front of you.',
    },
    {
      num: '02',
      title: 'Ask the question.',
      body: 'Write the decision in your own words. The whole decision turns on that sentence, kept in view.',
    },
    {
      num: '03',
      title: 'The panel argues.',
      body: 'Experts drawn from that material are paired over what their documents share and argue in passes. Every turn lands on the map before the next pass reads it.',
    },
    {
      num: '04',
      title: 'The answer is filed.',
      body: 'A position, the confidence behind it, the strongest case against it, who held which view, and every source.',
    },
  ]

  return (
    <Band tone="page" id="how-it-works" aria-labelledby="how-heading">
      <div className="shell">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <Eyebrow>How it works</Eyebrow>
            <h2 id="how-heading" className={`${H2} mt-3`}>
              Four movements, always in the same order.
            </h2>
          </div>
          <p className="max-w-[48ch] font-ui text-body-sm text-ink-2">
            Add your material, ask the question, let the panel argue, file the answer.
          </p>
        </div>

        <ol className="mt-12 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((step) => (
            <li key={step.num} className={`${ruleClasses('top')} pt-5`}>
              <p className="tnum font-mono text-mono text-ink-3">{step.num}</p>
              <h3 className="mt-3 font-display text-heading text-ink">{step.title}</h3>
              <p className="mt-2 max-w-[34ch] font-ui text-body-sm text-ink-2">{step.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </Band>
  )
}

function ChatBubble({ from, children }: { from: 'you' | 'them'; children: ReactNode }) {
  return (
    <div className={from === 'you' ? 'flex justify-end' : 'flex justify-start'}>
      <p
        className={`max-w-[40ch] rounded-lg px-4 py-2.5 font-ui text-body-sm ${
          from === 'you' ? 'bg-paper text-ink shadow-card' : 'bg-bone text-ink-2'
        }`}
      >
        {children}
      </p>
    </div>
  )
}

/**
 * The difference — drawn, not written. The conversation is the narrow side and fades; the filed
 * decision is the wider, fully legible side. The asymmetry is the argument.
 */
function Difference() {
  return (
    <Band tone="band" id="difference" aria-labelledby="difference-heading">
      <div className="shell">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <Eyebrow>The difference</Eyebrow>
            <h2 id="difference-heading" className={`${H2} mt-3`}>
              Not a conversation. A filed decision.
            </h2>
          </div>
          <p className="max-w-[48ch] font-ui text-body-sm text-ink-2">
            Two things can end the same session. Only one of them leaves you holding something.
          </p>
        </div>

        <div className="mt-12 grid gap-10 lg:grid-cols-[5fr_7fr] lg:gap-16">
          <div className="opacity-70">
            <p className="font-ui text-label uppercase text-ink-3">A conversation</p>
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
            <p className="mt-5 font-mono text-micro uppercase tracking-[0.06em] text-ink-3">
              ▸ 14 more messages · no answer · nothing to keep
            </p>
            <p className="mt-2 max-w-[44ch] font-ui text-body-sm text-ink-2">
              …and the decision is still yours, made from a summary.
            </p>
          </div>

          <div>
            <p className="font-ui text-label uppercase text-ink-3">A filed decision</p>
            <div className="mt-4">
              <FiledSheet decision={FILED_DECISION} sample />
            </div>
            <p className="mt-5 font-mono text-micro uppercase tracking-[0.06em] text-ink-3">
              One sheet · the answer, the share behind it, the case against, the sources
            </p>
            <p className="mt-2 max-w-[48ch] font-ui text-body-sm text-ink-2">
              …and it is on your desk, with everything that produced it.
            </p>
          </div>
        </div>

        <p className="mt-12 max-w-[60ch] font-display text-heading text-ink">
          The difference is not the interface. It is what you are holding at the end.
        </p>
      </div>
    </Band>
  )
}

/** The anatomy — the verdict sheet is the diagram; four numbered callouts name its parts. */
function WhatYouGet() {
  const callouts = [
    {
      num: '01',
      title: 'The position',
      body: 'A word, a symbol, and the share behind it. Colour is never the only signal.',
    },
    {
      num: '02',
      title: 'The confidence',
      body: 'A weighted share, set in mono. It measures the panel’s agreement, not the truth. A split is filed as a split.',
    },
    {
      num: '03',
      title: 'The case against',
      body: 'The strongest argument on the other side, kept whole and given its own ruled block.',
    },
    {
      num: '04',
      title: 'The sources',
      body: 'Every claim traces back to a section of your material. The document that leaves is the document you read.',
    },
  ]

  return (
    <Band tone="page" id="answer" aria-labelledby="answer-heading">
      <div className="shell">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <Eyebrow>What you get</Eyebrow>
            <h2 id="answer-heading" className={`${H2} mt-3`}>
              Four objects, every time.
            </h2>
          </div>
          <p className="max-w-[48ch] font-ui text-body-sm text-ink-2">
            None of them is a chat you have to keep asking.
          </p>
        </div>

        <div className="mt-12 grid gap-10 lg:grid-cols-[7fr_5fr] lg:items-start lg:gap-16">
          <div className="flex justify-center">
            <div className="w-full max-w-[600px]">
              <FiledSheet decision={FILED_DECISION} sample />
            </div>
          </div>

          <ol className={`grid content-start ${ruleClasses('bottom')}`}>
            {callouts.map((callout) => (
              <li key={callout.num} className={`${ruleClasses('top')} grid grid-cols-[40px_1fr] gap-4 py-5`}>
                <span className="tnum font-mono text-mono text-ink-3">{callout.num}</span>
                <div>
                  <h3 className="font-ui text-body-sm font-semibold text-ink">{callout.title}</h3>
                  <p className="mt-1 font-ui text-body-sm text-ink-2">{callout.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </Band>
  )
}

/** The proof of process — a sticky heading and four ruled rows. No logo wall, no carousel. */
function Trust() {
  const proofs = [
    {
      num: '01',
      title: 'Every verdict shows its work.',
      body: 'The case against, the sources, and who held which view are part of the answer, not an appendix.',
    },
    {
      num: '02',
      title: 'Every run replays exactly.',
      body: 'Reopen a decision next month and it renders as it ended. The map is a view of stored truth, not a likeness.',
    },
    {
      num: '03',
      title: 'Your material stays yours.',
      body: 'The documents, the map, and every decision stay on the machine you start it on. The answer leaves as a document.',
    },
    {
      num: '04',
      title: 'Free to start · No card',
      body: 'The first decisions are free. A plan appears only when the material or the number of decisions outgrows the free tier.',
    },
  ]

  return (
    <Band tone="band" aria-labelledby="trust-heading">
      <div className="shell">
        <div className="grid gap-10 lg:grid-cols-[5fr_7fr] lg:gap-16">
          <div className="lg:sticky lg:top-28 lg:self-start">
            <Eyebrow>Why you can check it</Eyebrow>
            <h2 id="trust-heading" className={`${H2} mt-3`}>
              No borrowed credibility. The work is the proof.
            </h2>
            <p className="mt-4 max-w-[40ch] font-ui text-body-sm text-ink-2">
              There are no customer logos here yet. There are no invented benchmarks. What you can
              check is the mechanism itself.
            </p>
          </div>

          <ol className={`grid sm:grid-cols-2 lg:grid-cols-1 ${ruleClasses('bottom')}`}>
            {proofs.map((proof) => (
              <li key={proof.num} className={`${ruleClasses('top')} grid grid-cols-[48px_1fr] gap-5 py-6`}>
                <span className="tnum font-mono text-mono text-ink-3">{proof.num}</span>
                <div>
                  <h3 className="font-ui text-[17px] leading-[24px] font-semibold text-ink">{proof.title}</h3>
                  <p className="mt-1 max-w-[52ch] font-ui text-body-sm text-ink-2">{proof.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </Band>
  )
}

/** What it does, and what it does not. The absences are stated once, plainly. */
function Limits() {
  const does = [
    {
      title: 'It runs on your machine.',
      body: 'The documents, the map and every decision stay on the machine you start the tool on.',
    },
    {
      title: 'Every claim has a source.',
      body: 'Each answer names the material each expert argued from, traceable to the section it was read from.',
    },
    {
      title: 'Every decision is kept.',
      body: 'A finished decision reopens and renders exactly as it ended, pass by pass.',
    },
  ]
  const doesNot = [
    {
      title: 'It cannot invent a panel.',
      body: 'The experts are drawn only from what you add. With no documents there is no panel and no answer.',
    },
    {
      title: 'It does not guarantee the answer.',
      body: 'Confidence is the weighted share behind the position. It measures the panel, not the truth; a split is filed as a split.',
    },
    {
      title: 'It does not keep the text from your provider.',
      body: 'The text your experts read and write goes to the provider you configure. Point it at a provider on your own machine if it must not leave.',
    },
  ]

  const column = (heading: string, lines: typeof does) => (
    <div>
      <h3 className="font-ui text-label uppercase text-ink-3">{heading}</h3>
      <ul className={`${ruleClasses('both')} mt-4`}>
        {lines.map((line) => (
          <li key={line.title} className={`${ruleClasses('top', 'hair')} py-4`}>
            <p className="font-ui text-body-sm font-semibold text-ink">{line.title}</p>
            <p className="mt-1 max-w-[52ch] font-ui text-body-sm text-ink-2">{line.body}</p>
          </li>
        ))}
      </ul>
    </div>
  )

  return (
    <Band tone="page" aria-labelledby="limits-heading">
      <div className="shell">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <Eyebrow>The honest part</Eyebrow>
            <h2 id="limits-heading" className={`${H2} mt-3`}>
              What it does. What it does not do.
            </h2>
          </div>
          <p className="max-w-[48ch] font-ui text-body-sm text-ink-2">
            A tool you can trust is a tool that tells you where it stops.
          </p>
        </div>

        <div className="mt-12 grid gap-10 md:grid-cols-2 md:gap-16">
          {column('What it does', does)}
          {column('What it does not do', doesNot)}
        </div>
      </div>
    </Band>
  )
}

/** Where it earns its keep — four ruled editorial rows, alternating on desktop. */
function UseCases() {
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
    <Band tone="band" aria-labelledby="cases-heading">
      <div className="shell">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <Eyebrow>Use cases</Eyebrow>
            <h2 id="cases-heading" className={`${H2} mt-3`}>
              Where it earns its keep.
            </h2>
          </div>
          <p className="max-w-[48ch] font-ui text-body-sm text-ink-2">
            The decisions that turn on documents you already hold.
          </p>
        </div>

        <ol className={`mt-12 ${ruleClasses('bottom')}`}>
          {cases.map((item, index) => {
            const flipped = index % 2 === 1
            return (
              <li
                key={item.question}
                className={`${ruleClasses('top')} grid gap-3 py-8 lg:grid-cols-[56px_1fr_1fr_180px] lg:items-start lg:gap-8`}
              >
                <span className="tnum font-mono text-mono text-ink-3">
                  {String(index + 1).padStart(2, '0')}
                </span>
                <h3
                  className={`font-display text-[28px] leading-[34px] tracking-[-0.02em] text-ink ${
                    flipped ? 'lg:order-3' : ''
                  }`}
                >
                  {item.question}
                </h3>
                <p
                  className={`max-w-[46ch] font-ui text-body-sm text-ink-2 ${flipped ? 'lg:order-2' : ''}`}
                >
                  {item.body}
                </p>
                <span
                  className={`font-mono text-micro uppercase tracking-[0.06em] text-ink-3 ${
                    flipped ? 'lg:order-4' : ''
                  }`}
                >
                  {item.replaces}
                </span>
              </li>
            )
          })}
        </ol>
      </div>
    </Band>
  )
}

/** The questions owners actually ask — native details, the kit's top rule, the kit's +/− marker. */
function Questions() {
  const items = [
    {
      q: 'What do I need to start?',
      a: 'One document and one decision you cannot look up. The panel is drawn from your material; with no material there is no panel.',
    },
    {
      q: 'Is this a chatbot?',
      a: 'No. You do not message it back and forth. You add your documents, ask one question, and read a filed answer with the case against it.',
    },
    {
      q: 'How is the confidence calculated?',
      a: 'It is the weighted share behind the position. It measures the panel’s agreement, not the truth. A split is filed as a split.',
    },
    {
      q: 'Where does my material go?',
      a: 'The documents, the map and every decision stay on the machine you start it on. The text your experts read and write goes to the provider you configure.',
    },
    {
      q: 'What does it cost?',
      a: 'Free to start · No card. The first decisions are free. A plan appears only when the material or the number of decisions outgrows the free tier.',
    },
    {
      q: 'Can I take the answer with me?',
      a: 'Yes. The answer leaves as a document — the same one you read on screen.',
    },
  ]

  return (
    <Band tone="page" dense id="questions" aria-labelledby="faq-heading">
      <div className="shell">
        <div className="grid gap-10 lg:grid-cols-[5fr_7fr] lg:gap-16">
          <div className="lg:sticky lg:top-28 lg:self-start">
            <Eyebrow>Questions</Eyebrow>
            <h2 id="faq-heading" className={`${H2} mt-3`}>
              Good questions.
            </h2>
            <p className="mt-4 max-w-[38ch] font-ui text-body-sm text-ink-2">
              The questions owners actually ask, answered from how the product behaves — no more, no
              less.
            </p>
          </div>

          <div>
            {items.map((item, index) => (
              <Disclosure key={item.q} summary={item.q} defaultOpen={index === 0}>
                <p className="max-w-[68ch] font-ui text-body-sm text-ink-2">{item.a}</p>
              </Disclosure>
            ))}
          </div>
        </div>
      </div>
    </Band>
  )
}

/** The pine close — the page's only dark band, and one action. */
function Close() {
  return (
    <Band tone="dark" id="close" aria-labelledby="close-heading">
      <div className="shell">
        <div className="grid gap-10 lg:grid-cols-[7fr_5fr] lg:items-end lg:gap-16">
          <div>
            <Eyebrow dark>Start here</Eyebrow>
            <h2 id="close-heading" className="mt-3 max-w-[16ch] font-display text-display text-map-ink">
              Bring a question you can’t look up.
            </h2>
            <p className="mt-4 max-w-[46ch] font-ui text-body text-map-ink-2">
              Your documents, a panel drawn from them, and an answer filed with the case against.
            </p>
          </div>
          <div className="lg:justify-self-end">
            <Link
              to="/auth/signup?next=/new"
              data-action="close"
              className="inline-flex h-12 items-center justify-center rounded-md bg-map-accent px-6 font-ui text-body font-semibold text-map-ground transition-opacity duration-state hover:opacity-90"
            >
              Start your first decision
            </Link>
            <p className="mt-4 font-mono text-micro text-map-ink-2">Free to start · No card</p>
          </div>
        </div>
      </div>
    </Band>
  )
}

/** The footer — the wordmark, the product links, contact, and the edition line. No version number. */
function Footer() {
  return (
    <Band as="footer" tone="page" dense>
      <div className="shell">
        <div className={`${ruleClasses('top')} grid gap-10 pt-10 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr]`}>
          <div>
            <Link to="/" className="inline-flex items-center gap-2.5 text-ink" aria-label={WORDMARK}>
              <BrandMark />
              <span className="font-ui text-[18px] font-semibold tracking-[-0.01em]">{WORDMARK}</span>
            </Link>
            <p className="mt-3 max-w-[38ch] font-ui text-body-sm text-ink-2">
              A decision you can open again: your documents, a panel drawn from them, and the answer
              filed with the case against.
            </p>
            <p className="mt-4 font-mono text-micro text-ink-3">Local-first · Free to start · decision panel</p>
          </div>

          <div>
            <p className="font-ui text-label uppercase text-ink-3">Product</p>
            {SECTION_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="mt-3 block font-ui text-body-sm text-ink-2 hover:text-ink"
              >
                {link.label}
              </a>
            ))}
          </div>

          <div>
            <p className="font-ui text-label uppercase text-ink-3">Contact</p>
            <a
              href="mailto:hello@societas.example"
              className="mt-3 block font-ui text-body-sm text-ink-2 hover:text-ink"
            >
              Talk to us
            </a>
            <Link to="/auth/signin" className="mt-3 block font-ui text-body-sm text-ink-2 hover:text-ink">
              Sign in
            </Link>
            <Link
              to="/auth/signup?next=/new"
              className="mt-3 block font-ui text-body-sm text-ink-2 hover:text-ink"
            >
              Start your first decision
            </Link>
          </div>
        </div>
      </div>
    </Band>
  )
}

/**
 * The homepage, at `/`. The order is the order a stranger decides in: the feeling, what is true,
 * the cost of the status quo, the mechanism, the difference, the deliverable, the proof, the
 * limits, the places it earns its keep, the questions, the close.
 */
export default function Hero() {
  return (
    <div className="hero-page min-h-screen bg-bone text-ink">
      <Nav />
      <HeroSection />
      <Facts />
      <Problem />
      <HowItWorks />
      <Difference />
      <WhatYouGet />
      <Trust />
      <Limits />
      <UseCases />
      <Questions />
      <Close />
      <Footer />
    </div>
  )
}
