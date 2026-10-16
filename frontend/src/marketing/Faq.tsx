import Disclosure from '../components/ui/Disclosure'
import RuledBlock from '../components/ui/RuledBlock'
import { sections } from './copy'

/**
 * Questions owners ask (DSPEC §7.1 §6) — an accordion on ruled baselines, answered from real
 * behaviour only. Each item is a `ui/Disclosure` (a `<button aria-expanded>` over its ruled
 * baseline); the first is open so the page is not a wall of closed rows.
 */
export default function Faq() {
  const faq = sections.faq
  return (
    <section>
      <h2 className="text-title text-ink">{faq.heading}</h2>
      <p className="mt-2 max-w-[68ch] text-body-lg text-ink-2">{faq.note}</p>

      <RuledBlock className="mt-4">
        {/* Disclosure draws its own bottom rule per item; the last one is dropped so the block's own
            bottom rule is not doubled. */}
        <div className="[&>div:last-child]:border-b-0">
          {faq.items.map((item, index) => (
            <Disclosure key={item.q} summary={item.q} defaultOpen={index === 0}>
              <p className="max-w-[68ch] text-body text-ink-2">{item.a}</p>
            </Disclosure>
          ))}
        </div>
      </RuledBlock>
    </section>
  )
}
