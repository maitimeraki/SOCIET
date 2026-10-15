import RuledBlock from '../components/ui/RuledBlock'
import { sections } from './copy'

/**
 * The differentiator (plan §3.1 §5, brief §1). Builds on `ui/Table.tsx` — the traverse log's ruled
 * columns — and states truthful differences only: no invented competitor capability, no benchmark.
 *
 * TODO(Task 17b): the rows are "Single chatbot", "Prompt-chained agents", "Societas" against the
 * columns structure, provenance, dissent, verdict confidence.
 */
export default function ComparisonTable() {
  return (
    <section>
      <h2 className="text-title text-ink">{sections.comparison.heading}</h2>
      <RuledBlock className="mt-4">
        <p className="max-w-[68ch]">{sections.comparison.note}</p>
      </RuledBlock>
    </section>
  )
}
