import RuledBlock from '../components/ui/RuledBlock'
import { sections } from './copy'

/**
 * The traverse (DSPEC §7.1 §3) and the legend of what you get (§7.1 §4) — both are keyed ruled
 * lines about the same mechanism, so they live in one section.
 *
 * TODO(Task 17b): fill the bodies. §3 is the mechanism in four ruled steps
 * (record → stations → lines of sight → the fix), each a `RuledBlock` carrying a legend key; §4 is
 * five ruled lines, symbol + word: verdict, confidence, dissent, provenance, replay.
 */
export default function HowItWorks() {
  return (
    <section>
      <h2 className="text-title text-ink">{sections.howItWorks.heading}</h2>
      <RuledBlock className="mt-4">
        <p className="max-w-[68ch]">{sections.howItWorks.note}</p>
      </RuledBlock>
    </section>
  )
}
