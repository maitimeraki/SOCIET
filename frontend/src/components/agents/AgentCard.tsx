import type { AgentProfile } from '../../run/events'
import PositionMark from '../ui/PositionMark'
import Chip from '../ui/Chip'
import Meter from '../ui/Meter'

export default function AgentCard({ profile, onOpen }: { profile: AgentProfile; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full border-t border-ink-4 pt-4 text-left transition-colors duration-state hover:bg-ground-2"
    >
      <span className="flex items-center justify-between gap-2">
        <span className="text-body text-ink">
          {profile.identity.name} · {profile.identity.archetype.toLowerCase()}
        </span>
        <PositionMark position={profile.stance} size="sm" ground="light" />
      </span>
      <span className="mt-2 line-clamp-2 block text-body text-ink-2">{profile.bio}</span>
      <span className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
        <Meter label="conf" value={profile.confidence} display={profile.confidence.toFixed(2)} />
        <Meter label="conv" value={profile.conviction} display={profile.conviction.toFixed(2)} />
        <Meter label="cior" value={(profile.cior + 1) / 2} display={profile.cior.toFixed(1)} />
      </span>
      <span className="mt-3 flex flex-wrap gap-1">
        {profile.domain_tags.map((tag) => (
          <Chip key={tag}>{tag}</Chip>
        ))}
      </span>
    </button>
  )
}
