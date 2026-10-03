import type { RunState } from '../../run/reducer'
import { rosterById } from '../../run/selectors'
import { fmtScore } from '../../utils/format'
import { asStance } from '../../run/events'
import StanceChip from '../common/StanceChip'

export default function FinalStanceTable({ run }: { run: RunState }) {
  const byName = rosterById(run)
  const rows = Object.entries(run.verdict?.finalStances ?? {})
  if (rows.length === 0) return <p className="text-body text-paper-mute">No final stances recorded.</p>
  return (
    <table className="w-full border-collapse text-body">
      <thead>
        <tr className="text-label uppercase text-paper-mute">
          <th className="py-2 pr-4 text-left font-medium">Agent</th>
          <th className="py-2 pr-4 text-left font-medium">Archetype</th>
          <th className="py-2 pr-4 text-left font-medium">Final</th>
          <th className="tnum py-2 text-right font-medium">Confidence</th>
        </tr>
      </thead>
      <tbody className="text-paper-dim">
        {rows.map(([agent, stance]) => {
          const profile = byName.get(agent)
          const lastConfidence = lastTurnConfidence(run, agent)
          return (
            <tr key={agent} className="border-t border-ink-700">
              <td className="py-2.5 pr-4 text-paper">{agent}</td>
              <td className="py-2.5 pr-4">{profile?.identity.archetype ?? '—'}</td>
              <td className="py-2.5 pr-4">
                <StanceChip stance={asStance(stance)} size="sm" />
              </td>
              <td className="tnum py-2.5 text-right font-mono text-mono">
                {lastConfidence === null ? '—' : fmtScore(lastConfidence)}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function lastTurnConfidence(run: RunState, agent: string): number | null {
  for (let index = run.rounds.length - 1; index >= 0; index -= 1) {
    const turn = run.rounds[index].turns.find((entry) => entry.agent_name === agent)
    if (turn) return turn.confidence
  }
  return null
}
