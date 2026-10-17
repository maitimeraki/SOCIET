import EmptyState from '../components/ui/EmptyState'

/**
 * §8.5 Verdicts — the outcome of a decision: its stance, its confidence and what it means, where the
 * Decisions section shows the process. The reading view lands in this section's own task, so this
 * states the section's purpose rather than pretending a verdict exists.
 */
export default function ResultsSection() {
  return (
    <div className="space-y-6">
      <h1 className="font-titling text-display text-ink">Verdicts</h1>
      <EmptyState line="The outcome of each decision — its stance, its confidence, and the strongest case against it. A verdict appears here when a decision finishes." />
    </div>
  )
}
