import type { AgentView } from '../../run/events'
import PositionMark from '../ui/PositionMark'
import Chip from '../ui/Chip'
import { ruleClasses } from '../ui/Rule'

export default function ProfileCard({ profile }: { profile: AgentView }) {
  return (
    <article className={`${ruleClasses('top')} pt-4`}>
      <header className="flex items-center justify-between gap-2">
        <span className="text-body text-ink">
          {profile.name} · {profile.role.toLowerCase()}
        </span>
        <PositionMark position={profile.stance} size="sm" ground="light" />
      </header>
      <p className="mt-2 line-clamp-2 text-body text-ink-2">{profile.bio}</p>
      <div className="mt-2 flex flex-wrap items-center gap-1">
        <Chip>{profile.type}</Chip>
      </div>
    </article>
  )
}
