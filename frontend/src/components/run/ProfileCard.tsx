import { SealCheck } from '@phosphor-icons/react'
import type { AgentProfile } from '../../run/events'
import StanceChip from '../common/StanceChip'
import Tag from '../ui/Tag'

export default function ProfileCard({ profile }: { profile: AgentProfile }) {
  const sources = profile.summary_provenance ?? []
  return (
    <article className="rounded-[6px] border border-ink-700 bg-ink-900 p-4">
      <header className="flex items-center justify-between gap-2">
        <span className="text-body text-paper">
          {profile.identity.name} · {profile.identity.archetype.toLowerCase()}
        </span>
        <StanceChip stance={profile.stance} size="sm" />
      </header>
      <p className="mt-2 line-clamp-2 text-body text-paper-dim">{profile.bio}</p>
      <div className="mt-2 flex flex-wrap items-center gap-1">
        <span className="text-micro text-paper-mute">from cluster:</span>
        {profile.domain_tags.map((tag) => (
          <Tag key={tag}>{tag}</Tag>
        ))}
      </div>
      <div className="mt-2 text-micro">
        {sources.length > 0 ? (
          <span className="flex items-start gap-1.5 text-paper-mute">
            <SealCheck size={12} className="mt-0.5 shrink-0 text-brass" aria-hidden="true" />
            sources: {sources.map((source) => `${source.title}${source.breadcrumb ? ` §${source.breadcrumb}` : ''}`).join(' · ')}
          </span>
        ) : (
          <span className="text-paper-faint">no provenance recovered</span>
        )}
      </div>
    </article>
  )
}
