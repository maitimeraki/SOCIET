import { sections } from './copy'

/**
 * Trust — the mechanism and its limits, with no borrowed credibility. There are no logos,
 * testimonials, case studies or certifications, so the section shows what the product verifiably
 * does and the limits that follow from how it works.
 */
export default function TrustSection() {
  const trust = sections.trust
  return (
    <section aria-labelledby="trust-heading">
      <h2 id="trust-heading" className="font-titling text-title text-ink">
        {trust.heading}
      </h2>
      <p className="mt-2 max-w-[68ch] font-record text-[18px] leading-[28px] text-ink-2">{trust.note}</p>

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <div className="m-card p-5">
          <h3 className="font-titling text-heading text-ink">{trust.doesTitle}</h3>
          <ul className="mt-3 divide-y divide-border">
            {trust.does.map((line) => (
              <li key={line.label} className="py-3 first:pt-0 last:pb-0">
                <p className="font-titling font-medium text-ink">{line.label}</p>
                <p className="mt-1 max-w-[68ch] font-record text-[18px] leading-[28px] text-ink-2">{line.body}</p>
              </li>
            ))}
          </ul>
        </div>
        <div className="m-card p-5">
          <h3 className="font-titling text-heading text-ink">{trust.doesNotTitle}</h3>
          <ul className="mt-3 divide-y divide-border">
            {trust.doesNot.map((line) => (
              <li key={line.label} className="py-3 first:pt-0 last:pb-0">
                <p className="font-titling font-medium text-ink">{line.label}</p>
                <p className="mt-1 max-w-[68ch] font-record text-[18px] leading-[28px] text-ink-2">{line.body}</p>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}
