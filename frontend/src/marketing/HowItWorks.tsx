import type { ReactNode } from 'react'
import Legend from '../components/common/Legend'
import RuledBlock from '../components/ui/RuledBlock'
import { sections } from './copy'

/**
 * The traverse (DSPEC §7.1 §3) and the legend of what you get (§7.1 §4). Both are keyed ruled lines
 * about the same mechanism, so they live in one section.
 *
 * §3 — the mechanism in four ruled steps (record → stations → lines of sight → the fix), each a
 * `RuledBlock` carrying a legend key (A–D) that matches a `Legend` entry. Every claim is real
 * product behaviour, not a promise.
 *
 * §4 — the legend of what you get: five ruled lines, symbol + word, keyed 1–5.
 *
 * The marks are authored geometry in the survey's own grammar (a ruled record, a station triangle, a
 * traced sightline, the fix ring) — never a picture, never an icon standing in for the world. Colour
 * is absent here by design, so no hue is introduced and the legend law is satisfied trivially: every
 * mark sits beside its ink word.
 */

const mark = (children: ReactNode) => (
  <svg
    width={16}
    height={16}
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.5}
    strokeLinecap="round"
    aria-hidden="true"
    focusable="false"
  >
    {children}
  </svg>
)

const TRAVERSE_MARKS: Record<string, ReactNode> = {
  // A · record — a ruled record: the corpus the graph is read from.
  A: mark(<path d="M3 4.5h10M3 8h10M3 11.5h6" />),
  // B · stations — a triangulation station.
  B: mark(<path d="M8 2.6 14 13.4H2z" />),
  // C · lines of sight — a sightline traced between two stations.
  C: mark(
    <>
      <path d="M3.5 12.5 12.5 3.5" />
      <circle cx="3.5" cy="12.5" r="1.4" fill="currentColor" stroke="none" />
      <circle cx="12.5" cy="3.5" r="1.4" fill="currentColor" stroke="none" />
    </>,
  ),
  // D · the fix — the closure ring and the plotted centre.
  D: mark(
    <>
      <circle cx="8" cy="8" r="5.2" />
      <circle cx="8" cy="8" r="1.6" fill="currentColor" stroke="none" />
    </>,
  ),
}

const GAIN_MARKS: Record<string, ReactNode> = {
  // verdict — the fix mark.
  1: mark(
    <>
      <circle cx="8" cy="8" r="5.2" />
      <circle cx="8" cy="8" r="1.6" fill="currentColor" stroke="none" />
    </>,
  ),
  // confidence — a ruled scale.
  2: mark(
    <>
      <path d="M2 11.5h12" />
      <path d="M4.5 11.5V6M8 11.5V4M11.5 11.5V7.5" />
    </>,
  ),
  // dissent — a hatched patch, the relief left uncertain.
  3: mark(<path d="M2.5 4h11M2.5 7.5h11M2.5 11h11" strokeDasharray="1.6 1.6" />),
  // provenance — a contents map: a source linked back into the record.
  4: mark(
    <>
      <circle cx="4" cy="4" r="1.6" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none" />
      <path d="M4 4h8v8" />
    </>,
  ),
  // replay — a return arrow: the run redrawn.
  5: mark(
    <>
      <path d="M12.6 8a4.6 4.6 0 1 1-1.6-3.5" />
      <path d="M13.2 2.2v3h-3" />
    </>,
  ),
}

export default function HowItWorks() {
  const { heading, note, steps, traverseLegendTitle, gainsTitle, gains } = sections.howItWorks
  return (
    <section>
      <h2 className="text-title text-ink">{heading}</h2>
      <p className="mt-2 max-w-[68ch] text-body-lg text-ink-2">{note}</p>

      <div className="mt-6 space-y-3">
        {steps.map((step) => (
          <RuledBlock key={step.key} legendKey={step.key} title={step.title}>
            <p className="max-w-[68ch]">{step.body}</p>
          </RuledBlock>
        ))}
      </div>

      <Legend
        className="mt-4"
        title={traverseLegendTitle}
        entries={steps.map((step) => ({
          key: step.key,
          symbol: TRAVERSE_MARKS[step.key],
          label: step.title.toLowerCase(),
        }))}
      />

      <RuledBlock className="mt-8" title={gainsTitle}>
        <ul className="divide-y divide-ink-4">
          {gains.map((gain) => (
            <li key={gain.key} className="flex gap-3 py-2 first:pt-0 last:pb-0">
              <span className="mt-0.5 shrink-0 text-ink-3" aria-hidden="true">
                {GAIN_MARKS[gain.key]}
              </span>
              <p className="max-w-[68ch]">
                <span className="font-measurement text-mono text-ink-3">{gain.key}</span>{' '}
                <span className="font-medium text-ink">{gain.label}</span> — {gain.body}
              </p>
            </li>
          ))}
        </ul>
      </RuledBlock>
    </section>
  )
}
