import { sections } from './copy'

/**
 * The record — the shape of a filed decision, not a fabricated sample. There is no real case study
 * to show, so the section proves the mechanism by showing what the document holds: the answer, the
 * opposing case, the positions, the sources and the passes. No invented answer, number, source or
 * capture is rendered.
 */
export default function RecordSheet() {
  const record = sections.record
  return (
    <section aria-labelledby="record-heading">
      <h2 id="record-heading" className="font-titling text-title text-ink">
        {record.heading}
      </h2>
      <p className="mt-2 max-w-[68ch] text-body-lg text-ink-2">{record.note}</p>

      <article className="m-card mt-4 p-5">
        <header className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 border-b border-border pb-3">
          <p className="font-titling text-label uppercase tracking-[0.14em] text-ink">{record.filedLabel}</p>
          <p className="font-measurement text-mono text-ink-3">{record.shapeLabel}</p>
        </header>

        <dl className="mt-4 divide-y divide-border">
          {record.fields.map((field) => (
            <div key={field.key} className="grid gap-1 py-3 sm:grid-cols-[10rem_1fr] sm:gap-4">
              <dt className="font-titling font-medium text-ink">{field.label}</dt>
              <dd className="text-body text-ink-2">{field.body}</dd>
            </div>
          ))}
        </dl>

        <footer className="mt-2 border-t border-border pt-3">
          <p className="font-titling font-medium text-ink">{record.keepLabel}</p>
          <p className="mt-1 text-body text-ink-2">{record.keepNote}</p>
        </footer>
      </article>
    </section>
  )
}
