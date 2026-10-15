import RuledBlock from '../components/ui/RuledBlock'
import { sections } from './copy'

/**
 * Questions owners ask (DSPEC §7.1 §6) — an accordion on ruled baselines, answered from real
 * behaviour only.
 *
 * TODO(Task 17b): the accordion body (`ui/Disclosure.tsx`), answers grounded in how the product
 * behaves. The incumbent `HomePage` FAQ held ten verified answers; they are in git history at the
 * commit before `HomePage.tsx` was retired.
 */
export default function Faq() {
  return (
    <section>
      <h2 className="text-title text-ink">{sections.faq.heading}</h2>
      <RuledBlock className="mt-4">
        <p className="max-w-[68ch]">{sections.faq.note}</p>
      </RuledBlock>
    </section>
  )
}
