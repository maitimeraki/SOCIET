import { SealCheck } from '@phosphor-icons/react'
import type { ProvenanceLink } from '../../run/events'

export default function ProvenanceList({ links }: { links: ProvenanceLink[] }) {
  if (links.length === 0) return <p className="text-body text-paper-faint">no provenance recovered</p>
  return (
    <ul className="space-y-2">
      {links.map((link) => (
        <li key={link.chunk_id} className="flex items-start gap-2 text-body text-paper-dim">
          <SealCheck size={14} className="mt-1 shrink-0 text-brass" aria-hidden="true" />
          <span>
            {link.title}
            {link.breadcrumb ? ` — ${link.breadcrumb}` : ''}
            <span className="tnum ml-2 font-mono text-micro text-paper-mute">{link.chunk_id}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}
