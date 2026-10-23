import Card from './Card'
import Chip from './Chip'
import Meter from './Meter'
import PositionMark from './PositionMark'
import type { Position } from './PositionMark'
import { ruleClasses } from './Rule'

/**
 * §14.2 — the filed decision, composed. One sheet: the question, the position as symbol + word,
 * the weighted share as a drawn meter with its figure, the case against, and the sources.
 *
 * Three surfaces share this primitive — the homepage's comparison panel, the auth page's right
 * column, and the dashboard's "The last answer" — so the two surfaces rhyme by construction
 * rather than by discipline.
 *
 * `sample` marks the sheet as **authored material**: it is a real filed decision about a named
 * other party, and house style rule 9 says authored material is labelled a worked example. The
 * chip and the caption are therefore the sheet's, not the caller's.
 */
export type FiledDecision = {
  question: string
  position: Position
  share: number
  caseAgainst: string
  sources: string
}

export default function FiledSheet({
  decision,
  sample = false,
  className = '',
}: {
  decision: FiledDecision
  sample?: boolean
  className?: string
}) {
  const share = decision.share.toFixed(2)
  return (
    <Card as="article" pad={24} radius="lg" className={className}>
      <div className="flex items-start justify-between gap-3">
        <p className="font-measurement text-mono uppercase tracking-[0.14em] text-ink-3">The decision</p>
        {sample ? (
          <Chip tone="neutral" className="uppercase tracking-[0.14em]">
            Worked example
          </Chip>
        ) : null}
      </div>

      <p className="mt-2 font-record text-[19px] leading-[26px] text-ink">{decision.question}</p>

      <div className={`${ruleClasses('top')} mt-4 pt-4`}>
        <p className="font-measurement text-[11px] uppercase tracking-[0.14em] text-ink">
          <PositionMark position={decision.position} size="sm" ground="light" />
        </p>
        <Meter
          value={decision.share}
          label="share"
          display={share}
          tone="ink"
          width="full"
          className="mt-3"
        />
      </div>

      <div className={`${ruleClasses('top')} mt-4 pt-4`}>
        <p className="font-measurement text-mono uppercase tracking-[0.14em] text-caution">The case against</p>
        <p className="mt-1 font-titling text-[13px] leading-[20px] text-ink-2">{decision.caseAgainst}</p>
      </div>

      <div className={`${ruleClasses('top')} mt-4 pt-4`}>
        <p className="font-measurement text-mono uppercase tracking-[0.14em] text-ink-3">Sources</p>
        <p className="mt-1 font-measurement text-[11px] leading-[18px] text-ink-3">{decision.sources}</p>
      </div>

      {sample ? (
        <p className={`${ruleClasses('top')} mt-4 pt-3 font-measurement text-[11px] leading-[17px] text-ink-3`}>
          A worked example, prepared to show what a filed answer looks like.
        </p>
      ) : null}
    </Card>
  )
}
