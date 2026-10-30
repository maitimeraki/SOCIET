import type { TurnInfo } from '../../run/events'
import { asStance } from '../../run/events'
import { fmtScore } from '../../utils/format'
import PositionMark from '../ui/PositionMark'
import Emphasis from '../common/Emphasis'
import Chip from '../ui/Chip'
import { ruleClasses } from '../ui/Rule'

export default function TurnCard({ turn, round }: { turn: TurnInfo; round: number }) {
  const references = turn.references ?? []
  const counts = references.reduce<Record<string, number>>((acc, reference) => {
    acc[reference] = (acc[reference] ?? 0) + 1
    return acc
  }, {})
  return (
    <article
      aria-label={`Pass ${round} — ${turn.agent_name}, ${turn.stance}`}
      className={`${ruleClasses('top')} pt-3`}
    >
      <header className="flex items-center gap-2">
        <span className="text-body text-ink">{turn.agent_name}</span>
        <PositionMark position={asStance(turn.stance)} size="sm" ground="light" />
        <span className="tnum font-mono text-micro text-ink-3">{fmtScore(turn.confidence)}</span>
      </header>
      <Emphasis text={turn.content} className="mt-2 max-w-[66ch] select-text text-body-lg text-ink-2" />
      {references.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1">
          <span className="text-micro text-ink-3">cited:</span>
          {Object.entries(counts).map(([name, count]) => (
            <Chip key={name}>{count > 1 ? `${name} ×${count}` : name}</Chip>
          ))}
        </div>
      )}
    </article>
  )
}
