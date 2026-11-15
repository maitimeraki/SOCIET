import type { AgentView } from '../../run/events'
import { shownText } from '../../run/agentDisplay'
import PositionMark from '../ui/PositionMark'
import Chip from '../ui/Chip'
import Meter from '../ui/Meter'
import { ruleClasses } from '../ui/Rule'
import { Estimate } from './AgentFacts'

export default function AgentCard({ profile, onOpen }: { profile: AgentView; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`${ruleClasses('top')} w-full pt-4 text-left transition-colors duration-state hover:bg-sand`}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="text-body text-ink">
          {shownText(profile.name)} · {shownText(profile.role).toLowerCase()}
        </span>
        <PositionMark position={profile.stance} size="sm" ground="light" />
      </span>
      <span className="mt-2 line-clamp-2 block text-body text-ink-2">{shownText(profile.bio)}</span>
      <span className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1">
        <Meter label="str" value={profile.strength} display={profile.strength.toFixed(2)} />
        <Estimate value={profile.confidence} />
      </span>
      <span className="mt-3 flex flex-wrap gap-1">
        <Chip>{shownText(profile.type)}</Chip>
      </span>
    </button>
  )
}
