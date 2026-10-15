import type { ReactNode } from 'react'

export interface LegendEntry {
  /** Optional key matching a `RuledBlock`'s legend key, so a block and its legend entry are linkable. */
  key?: string
  /** The drawn mark. It is `aria-hidden` — the word beside it carries the meaning. */
  symbol: ReactNode
  label: string
}

/**
 * §6 The legend — **the one recurring component**. A real legend block (symbols + words) that appears
 * wherever mixed-colour data appears: it is the product's honest index, and it is what makes colour
 * legal at all. §3 says a hue with no legend entry does not exist; this is the entry. It doubles as
 * the accessibility key, so a symbol is never the only carrier of a distinction (§9).
 *
 * A legend is a ruled block like any other new surface — bounded top and bottom by hairlines, never
 * an enclosed box — and every label is ink: a legend *describes* colour, it does not set text in it.
 *
 * `entries` is generic on purpose. Stances are the common case (`<StanceSymbol>` gives the glyph),
 * but the same block keys entity types on the graph, states on the traverse, and anything else the
 * map needs to explain.
 */
export default function Legend({
  entries,
  title,
  className = '',
}: {
  entries: LegendEntry[]
  title?: ReactNode
  className?: string
}) {
  if (entries.length === 0) return null
  return (
    <section className={`border-y border-ink-4 py-2 ${className}`} aria-label={typeof title === 'string' ? title : undefined}>
      {title && <h3 className="mb-1.5 text-label uppercase text-ink-3">{title}</h3>}
      <ul className="flex flex-wrap items-baseline gap-x-4 gap-y-1.5">
        {entries.map((entry) => (
          <li key={entry.key ?? entry.label} className="inline-flex items-baseline gap-1.5 text-micro text-ink-2">
            <span className="inline-flex shrink-0 translate-y-px" aria-hidden="true">
              {entry.symbol}
            </span>
            {entry.key && <span className="font-measurement text-mono text-ink-3">{entry.key}</span>}
            {entry.label}
          </li>
        ))}
      </ul>
    </section>
  )
}

