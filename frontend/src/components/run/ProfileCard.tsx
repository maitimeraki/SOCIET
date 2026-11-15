import type { AgentView } from '../../run/events'
import { shownText, shownType } from '../../run/agentDisplay'
import PositionMark from '../ui/PositionMark'
import Chip from '../ui/Chip'
import Meter from '../ui/Meter'
import { ruleClasses } from '../ui/Rule'
import { Details, Estimate } from '../agents/AgentFacts'

export default function ProfileCard({ profile }: { profile: AgentView }) {
  return (
    <article className={`${ruleClasses('top')} pt-4`}>
      <header className="flex items-center justify-between gap-2">
        <span className="text-body text-ink">
          {shownText(profile.name)} · {shownText(profile.role).toLowerCase()}
        </span>
        <PositionMark position={profile.stance} size="sm" ground="light" />
      </header>
      <p className="mt-2 line-clamp-2 text-body text-ink-2">{shownText(profile.bio)}</p>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
        <Meter label="str" value={profile.strength} display={profile.strength.toFixed(2)} />
        <Estimate value={profile.confidence} />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1">
        <Chip>{shownType(profile.type)}</Chip>
      </div>
      <Details text={profile.details} className="mt-3 space-y-2 text-body text-ink-2" />
    </article>
  )
}
