import type { ReactNode } from 'react'
import { ruleClasses } from './Rule'

/**
 * §14.1 — a ruled term-and-value list. The terms and their values are read as pairs, and the
 * pairs are ruled off from one another by the kit's own hairline — a record, never a card: no
 * shadow, and no box around it.
 *
 * `tone` names the ground the list is read on: `light` is the light surfaces, `dark` is the
 * map's own surface, where the rule and the ink are the map's.
 */
export type DefinitionListTone = 'light' | 'dark'

export type DefinitionListItem = {
  term: ReactNode
  value: ReactNode
}

export default function DefinitionList({
  items,
  tone = 'light',
  className = '',
}: {
  items: DefinitionListItem[]
  tone?: DefinitionListTone
  className?: string
}) {
  const dark = tone === 'dark'
  const term = dark ? 'text-map-ink-2' : 'text-ink-3'
  const value = dark ? 'text-map-ink' : 'text-ink-2'
  return (
    <dl className={`${ruleClasses('around', tone)} ${className}`}>
      {items.map((item, index) => (
        // The pair is the unit: one term, one value, one rule between it and the next pair. The
        // pair is wrapped so the rule falls between the pairs and not between term and value.
        <div key={index} className="grid grid-cols-[140px_1fr] py-2 text-body">
          <dt className={term}>{item.term}</dt>
          <dd className={value}>{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}
