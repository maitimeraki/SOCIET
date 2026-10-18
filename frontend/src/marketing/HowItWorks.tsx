import { sections } from './copy'

/**
 * The mechanism in four movements and what a decision leaves behind. Every line is product
 * behaviour: the owner adds the documents, the experts are drawn from them, they argue in passes,
 * and the answer is filed with its opposing case, positions and sources. No figure is invented.
 */
export default function HowItWorks() {
  const how = sections.howItWorks
  return (
    <section aria-labelledby="how-heading">
      <h2 id="how-heading" className="font-titling text-title text-ink">
        {how.heading}
      </h2>
      <p className="mt-2 max-w-[68ch] text-body-lg text-ink-2">{how.note}</p>

      <h3 className="mt-6 font-titling text-label uppercase text-ink-3">{how.orderTitle}</h3>
      <ol className="mt-3 grid gap-4 sm:grid-cols-2">
        {how.steps.map((step) => (
          <li key={step.key} className="m-card p-5">
            <p className="font-measurement text-mono text-ink-3">{step.key}</p>
            <h4 className="mt-2 font-titling text-heading text-ink">{step.title}</h4>
            <p className="mt-2 text-body text-ink-2">{step.body}</p>
          </li>
        ))}
      </ol>

      <div className="m-card mt-6 p-5">
        <h3 className="font-titling text-heading text-ink">{how.gainsTitle}</h3>
        <ul className="mt-3 divide-y divide-border">
          {how.gains.map((gain) => (
            <li key={gain.key} className="flex gap-3 py-3 first:pt-0 last:pb-0">
              <span className="mt-0.5 shrink-0 font-measurement text-mono text-ink-3">{gain.key}</span>
              <p className="max-w-[68ch] text-body text-ink-2">
                <span className="font-titling font-medium text-ink">{gain.label}</span> — {gain.body}
              </p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
