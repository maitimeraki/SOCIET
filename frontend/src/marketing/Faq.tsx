import Disclosure from '../components/ui/Disclosure'
import { sections } from './copy'

/**
 * Questions owners ask — answered from product behaviour only. The answers carry no timing,
 * provider count, format list or other claim the build cannot verify. Each item is a
 * `ui/Disclosure` (a `<button aria-expanded>` over its ruled baseline); the first is open so the
 * page is not a wall of closed rows.
 */
export default function Faq() {
  const faq = sections.faq
  return (
    <section aria-labelledby="faq-heading">
      <h2 id="faq-heading" className="font-titling text-title text-ink">
        {faq.heading}
      </h2>
      <p className="mt-2 max-w-[68ch] text-body-lg text-ink-2">{faq.note}</p>

      <div className="m-card mt-4 px-5">
        {/* Disclosure draws its own bottom rule per item; the last one is dropped so the card edge
            is not doubled. */}
        <div className="[&>div:last-child]:border-b-0">
          {faq.items.map((item, index) => (
            <Disclosure
              key={item.q}
              summary={<span className="font-titling">{item.q}</span>}
              defaultOpen={index === 0}
            >
              <p className="max-w-[68ch] text-body text-ink-2">{item.a}</p>
            </Disclosure>
          ))}
        </div>
      </div>
    </section>
  )
}
