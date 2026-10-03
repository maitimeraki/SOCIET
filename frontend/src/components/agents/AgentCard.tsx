import type { AgentProfile } from '../../run/events'
import StanceChip from '../common/StanceChip'
import Tag from '../ui/Tag'
import MeterBar from './MeterBar'

export default function AgentCard({ profile, onOpen }: { profile: AgentProfile; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full rounded-[6px] border border-ink-700 bg-ink-900 p-4 text-left transition-colors hover:border-ink-600"
    >
      <span className="flex items-center justify-between gap-2">
        <span className="text-body text-paper">
          {profile.identity.name} · {profile.identity.archetype.toLowerCase()}
        </span>
        <StanceChip stance={profile.stance} size="sm" />
      </span>
      <span className="mt-2 line-clamp-2 block text-body text-paper-dim">{profile.bio}</span>
      <span className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
        <MeterBar label="conf" value={profile.confidence} display={profile.confidence.toFixed(2)} />
        <MeterBar label="conv" value={profile.conviction} display={profile.conviction.toFixed(2)} />
        <MeterBar label="cior" value={(profile.cior + 1) / 2} display={profile.cior.toFixed(1)} />
      </span>
      <span className="mt-3 flex flex-wrap gap-1">
        {profile.domain_tags.map((tag) => (
          <Tag key={tag}>{tag}</Tag>
        ))}
      </span>
    </button>
  )
}
