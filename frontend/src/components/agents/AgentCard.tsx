import type { AgentView } from '../../run/events'
import PositionMark from '../ui/PositionMark'
import Chip from '../ui/Chip'
import Meter from '../ui/Meter'
import { ruleClasses } from '../ui/Rule'

export default function AgentCard({ profile, onOpen }: { profile: AgentView; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`${ruleClasses('top')} w-full pt-4 text-left transition-colors duration-state hover:bg-sand`}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="text-body text-ink">
          {profile.name} · {profile.role.toLowerCase()}
        </span>
        <PositionMark position={profile.stance} size="sm" ground="light" />
      </span>
      <span className="mt-2 line-clamp-2 block text-body text-ink-2">{profile.bio}</span>
      <span className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
        <Meter label="conf" value={profile.confidence} display={profile.confidence.toFixed(2)} />
        <Meter label="str" value={profile.strength} display={profile.strength.toFixed(2)} />
      </span>
      <span className="mt-3 flex flex-wrap gap-1">
        <Chip>{profile.type}</Chip>
      </span>
    </button>
  )
}
