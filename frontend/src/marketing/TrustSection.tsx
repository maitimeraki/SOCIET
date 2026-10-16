import { ClockCounterClockwise, FileText, Plug, ShieldCheck, Warning } from '@phosphor-icons/react'
import type { Icon } from '@phosphor-icons/react'
import RuledBlock from '../components/ui/RuledBlock'
import { sections } from './copy'

/**
 * Security and trust (plan §3.1 §6, brief §1). Only claims the tool can keep: the corpus and graph
 * stay on the machine running it, the data is not used for training, the run history is the owner's,
 * and the provider is the owner's to choose. The SOC 2 line appears in its one legal form — in
 * progress, marked unverified — and never implies a certification that does not exist.
 *
 * The lines sit on ruled baselines (a hairline between each). The marks are the app's own icon
 * system (Phosphor, the same set `StateChip` and `Button` draw from), rendered in a symbol ink and
 * `aria-hidden` — the word beside each carries the meaning.
 */
const MARKS: Icon[] = [FileText, ShieldCheck, ClockCounterClockwise, Plug]

export default function TrustSection() {
  const trust = sections.trust
  return (
    <section>
      <h2 className="text-title text-ink">{trust.heading}</h2>
      <p className="mt-2 max-w-[68ch] text-body-lg text-ink-2">{trust.note}</p>

      <RuledBlock className="mt-4">
        <ul className="divide-y divide-ink-4">
          {trust.lines.map((line, index) => {
            const Mark = MARKS[index]
            return (
              <li key={line.label} className="flex gap-3 py-3 first:pt-0">
                <span className="mt-0.5 shrink-0 text-ink-3" aria-hidden="true">
                  <Mark size={16} />
                </span>
                <p className="max-w-[68ch]">
                  <span className="font-medium text-ink">{line.label}</span>
                  <span className="text-ink-2"> — {line.body}</span>
                </p>
              </li>
            )
          })}
          {/* The one legal form of the SOC 2 line: in progress, marked unverified, never implied complete. */}
          <li className="flex gap-3 py-3 last:pb-0">
            <span className="mt-0.5 shrink-0 text-ink-3" aria-hidden="true">
              <Warning size={16} />
            </span>
            <p className="max-w-[68ch]">
              <span className="font-medium text-ink">{trust.soc2}</span>{' '}
              <span className="font-measurement text-mono text-ink-3">({trust.soc2Marker})</span>
            </p>
          </li>
        </ul>
      </RuledBlock>
    </section>
  )
}
