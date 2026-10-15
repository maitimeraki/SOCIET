import RuledBlock from '../components/ui/RuledBlock'
import { sections } from './copy'

/**
 * The record (DSPEC §7.1 §5) — one finished run shown as a sheet: the fix, the closure, the dissent
 * hatched, and the contents map (the provenance index). The sample run is synthetic-labelled, like
 * the hero's.
 *
 * TODO(Task 17b): the record sheet itself, plus the Task 19 screenshot slots
 * (`<img width height loading="lazy" decoding="async">`) once real captures exist.
 */
export default function RecordSheet() {
  return (
    <section>
      <h2 className="text-title text-ink">{sections.record.heading}</h2>
      <RuledBlock className="mt-4">
        <p className="max-w-[68ch]">{sections.record.note}</p>
      </RuledBlock>
    </section>
  )
}
