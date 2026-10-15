import RuledBlock from '../components/ui/RuledBlock'
import { sections } from './copy'

/**
 * Security and trust (plan §3.1 §6, brief §1). Only claims the tool can keep: the corpus and graph
 * stay on the machine running it, the data is not used for training, and the run history is the
 * owner's. The SOC 2 line appears in its one legal form — in progress, marked unverified — and
 * never implies a certification that does not exist.
 *
 * TODO(Task 17b): the full five-line body and the ruled baselines.
 */
export default function TrustSection() {
  const trust = sections.trust
  return (
    <section>
      <h2 className="text-title text-ink">{trust.heading}</h2>
      <RuledBlock className="mt-4">
        <p className="max-w-[68ch]">{trust.note}</p>
        <p className="mt-3 font-measurement text-mono text-ink-3">
          {trust.soc2} ({trust.soc2Marker})
        </p>
      </RuledBlock>
    </section>
  )
}
