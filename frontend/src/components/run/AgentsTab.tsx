import { useState } from 'react'
import type { RunState } from '../../run/reducer'
import AgentCard from '../agents/AgentCard'
import AgentDrawer from '../agents/AgentDrawer'
import ActivationList from '../agents/ActivationList'
import EmptyState from '../ui/EmptyState'

export default function AgentsTab({ run }: { run: RunState }) {
  const [selected, setSelected] = useState<string | null>(null)
  const profile = selected ? run.roster.find((entry) => entry.identity.name === selected) ?? null : null
  if (run.roster.length === 0) {
    return <EmptyState line="No panel for this decision. Nothing in the corpus matched the question." />
  }
  return (
    <div className="space-y-8">
      <div className="flex items-baseline gap-3">
        <h2 className="text-body-sm font-semibold text-ink">The panel of this decision</h2>
        <span className="tnum font-mono text-micro text-ink-3">
          {run.roster.length} seated · {run.activations.reduce((sum, activation) => sum + activation.agents.length, 0)} activated
        </span>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {run.roster.map((entry) => (
          <AgentCard key={entry.agent_id} profile={entry} onOpen={() => setSelected(entry.identity.name)} />
        ))}
      </div>
      {run.activations.length > 0 && (
        <section>
          <h2 className="mb-3 text-body-sm font-semibold text-ink">Activated mid-debate</h2>
          <ActivationList activations={run.activations} />
        </section>
      )}
      <AgentDrawer profile={profile} open={profile !== null} onClose={() => setSelected(null)} />
    </div>
  )
}
