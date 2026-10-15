import FixMark from '../components/common/FixMark'
import StanceSymbol from '../components/common/StanceSymbol'
import RuledBlock from '../components/ui/RuledBlock'
import { sections } from './copy'

/**
 * The record (DSPEC §7.1 §5) — one finished run shown as a sheet: the fix, the closure, the dissent
 * hatched, and the contents map (the provenance index). The sample run is scripted and labelled
 * synthetic, like the hero's.
 *
 * The fix uses `FixMark` — the one mark that owns the word "verdict" (DSPEC §6) — so it appears
 * exactly once on the page, here. The stance word stays ink; the hue is the `StanceSymbol` beside it.
 */
export default function RecordSheet() {
  const record = sections.record
  return (
    <section>
      <h2 className="text-title text-ink">{record.heading}</h2>
      <p className="mt-2 max-w-[68ch] text-body-lg text-ink-2">{record.note}</p>

      <article className="mt-4">
        {/* The sheet's title block — the document's own frame, not a card. */}
        <header className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 border-y border-ink-4 py-2">
          <p className="font-titling text-label uppercase tracking-[0.14em] text-ink">{record.filedLabel}</p>
          <p className="font-measurement text-mono text-ink-3">{record.syntheticLabel}</p>
        </header>

        {/* The fix and the closure. */}
        <div className="mt-4 flex flex-wrap items-center gap-x-10 gap-y-4">
          <div>
            <p className="text-label uppercase text-ink-3">{record.fixLabel}</p>
            <p className="mt-1 flex items-baseline gap-2 font-titling text-title text-ink">
              <StanceSymbol stance={record.verdictWord} size={16} />
              {record.verdictWord}
            </p>
          </div>
          <div>
            <p className="text-label uppercase text-ink-3">{record.confidenceLabel}</p>
            <FixMark confidence={record.confidence} size={36} className="mt-1" />
          </div>
          <p className="font-measurement text-mono text-ink-3">
            {record.closureLabel} {record.closure}
          </p>
        </div>

        {/* The dissent, kept hatched rather than smoothed away. */}
        <RuledBlock className="mt-4">
          <div className="flex gap-3">
            <span className="mt-0.5 shrink-0" aria-hidden="true">
              <svg width={16} height={16} viewBox="0 0 16 16" focusable="false">
                <g stroke="var(--color-ink-4)" strokeWidth={1}>
                  <path d="M1 5.5 5.5 1M1 10.5 10.5 1M1 15.5 15.5 1M5 15.5 15.5 5M10 15.5 15.5 10" />
                </g>
              </svg>
            </span>
            <div>
              <p className="text-label uppercase text-ink-3">{record.dissentLabel}</p>
              <p className="mt-1 max-w-[68ch]">{record.dissent}</p>
            </div>
          </div>
        </RuledBlock>

        {/* The contents map — the provenance index back to the record. */}
        <div className="mt-4">
          <p className="text-label uppercase text-ink-3">{record.contentsLabel}</p>
          <ul className="mt-2 divide-y divide-ink-4">
            {record.contents.map((row) => (
              <li
                key={row.entity}
                className="flex flex-wrap items-baseline justify-between gap-x-4 py-1.5 font-measurement text-mono"
              >
                <span className="text-ink">{row.entity}</span>
                <span className="text-ink-3">{row.source}</span>
              </li>
            ))}
          </ul>
        </div>
      </article>

      {/* TODO(Task 19): replace this plate with the real capture —
          <img src="/img/plotting-table.webp" width={1280} height={720} loading="lazy" decoding="async"
               alt="The plotting table mid-survey" /> */}
      <figure className="mt-4">
        <div className="flex aspect-video items-center justify-center border border-ink-4 bg-survey-paper-2">
          <p className="font-measurement text-mono text-ink-3">{record.captureLabel}</p>
        </div>
        <figcaption className="mt-2 font-measurement text-mono text-ink-3">{record.captureNote}</figcaption>
      </figure>
    </section>
  )
}
