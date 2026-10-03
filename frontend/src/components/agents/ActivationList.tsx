import { Lightning } from '@phosphor-icons/react'
import type { RunActivation } from '../../run/reducer'

export default function ActivationList({ activations }: { activations: RunActivation[] }) {
  if (activations.length === 0) return null
  return (
    <ul className="space-y-2">
      {activations.flatMap((activation) =>
        activation.agents.map((agent) => (
          <li key={`${activation.round}-${agent}`} className="flex items-center gap-2 text-body text-paper-dim">
            <Lightning size={14} className="text-accent" aria-hidden="true" />
            {agent} — joined round {activation.round + 1}
            {activation.reasons[agent] ? ` — ${activation.reasons[agent]}` : ''}
          </li>
        )),
      )}
    </ul>
  )
}
