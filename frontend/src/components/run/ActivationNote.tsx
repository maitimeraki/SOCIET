import { Lightning } from '@phosphor-icons/react'

export default function ActivationNote({
  round,
  agents,
  reasons,
}: {
  round: number
  agents: string[]
  reasons: Record<string, string>
}) {
  const reason = agents.map((agent) => reasons[agent]).find(Boolean)
  return (
    <p className="flex items-center gap-2 text-micro text-accent">
      <Lightning size={14} aria-hidden="true" />
      {agents.length} {agents.length === 1 ? 'voice' : 'voices'} joined for round {round + 1}
      {reason ? ` — ${reason}` : ''}.
    </p>
  )
}
