import EmptyState from '../components/ui/EmptyState'
import RuledBlock from '../components/ui/RuledBlock'

/**
 * §8.6 Panel — the experts a decision is argued by. §8.6's rule: a section that implies continuity
 * that does not exist is worse than a section that says "not yet", so the honesty notice leads and the
 * experts themselves land in this section's own task.
 */
export default function PanelSection() {
  return (
    <div className="space-y-6">
      <h1 className="font-titling text-display text-ink">Panel</h1>
      <RuledBlock>
        Your panel is convened fresh for each decision, from your own documents. A panel that persists across
        decisions isn't built yet.
      </RuledBlock>
      <EmptyState line="No panel yet. Start a decision and your panel is convened from your own documents." />
    </div>
  )
}
