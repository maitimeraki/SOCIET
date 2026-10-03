import type { TurnInfo } from '../../run/events'
import { fmtScore } from '../../utils/format'
import StanceChip, { asStance } from '../common/StanceChip'
import Tag from '../ui/Tag'

export default function TurnCard({ turn, round }: { turn: TurnInfo; round: number }) {
  const references = turn.references ?? []
  const counts = references.reduce<Record<string, number>>((acc, reference) => {
    acc[reference] = (acc[reference] ?? 0) + 1
    return acc
  }, {})
  return (
    <article
      aria-label={`Round ${round} — ${turn.agent_name}, ${turn.stance}`}
      className="rounded-[6px] border border-ink-700 bg-ink-900 p-3"
    >
      <header className="flex items-center gap-2">
        <span className="text-body text-paper">{turn.agent_name}</span>
        <StanceChip stance={asStance(turn.stance)} size="sm" />
        <span className="tnum font-mono text-micro text-paper-mute">{fmtScore(turn.confidence)}</span>
      </header>
      <p className="mt-2 max-w-[66ch] select-text text-body-lg text-paper-dim">{turn.content}</p>
      {references.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1">
          <span className="text-micro text-paper-mute">cited:</span>
          {Object.entries(counts).map(([name, count]) => (
            <Tag key={name}>{count > 1 ? `${name} ×${count}` : name}</Tag>
          ))}
        </div>
      )}
    </article>
  )
}
