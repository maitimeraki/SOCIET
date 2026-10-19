import { SealCheck } from '@phosphor-icons/react'
import type { ProvenanceLink } from '../../run/events'

export default function ProvenanceList({ links }: { links: ProvenanceLink[] }) {
  if (links.length === 0) return <p className="text-body text-ink-3">no provenance recovered</p>
  return (
    <ul className="space-y-2">
      {links.map((link) => (
        <li key={link.chunk_id} className="flex items-start gap-2 text-body text-ink-2">
          <SealCheck size={14} className="mt-1 shrink-0 text-warn" aria-hidden="true" />
          <span>
            {link.title}
            {link.breadcrumb ? ` — ${link.breadcrumb}` : ''}
            <span className="tnum ml-2 font-measurement text-micro text-ink-3">{link.chunk_id}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}
