import type { ReactNode } from 'react'
import { ruleClasses } from './Rule'

/**
 * §6 Cards are absent by law. Content sits in a **ruled block** — bounded top and bottom by hairline
 * rules, never an enclosed bordered box (there are no side rules) — carrying a **legend key** (a
 * letter or number that matches an entry in `Legend`). This is the card replacement for every new
 * surface; the boxed components the deep in-app views already use are untouched.
 *
 * The rules are the kit's own (`Rule side="both"`), so a record's edge is the same hairline every
 * other record in the product draws — the rule token, never a hand-rolled border.
 *
 * The key is *not* hidden from assistive tech: the legend doubles as the accessibility key, so the
 * key is how a reader connects this block to its legend entry.
 *
 * `title` renders as an `h3` — the level a block takes under a page `h2`. A page that needs another
 * level passes no `title` and puts its own heading in `children`.
 */
export default function RuledBlock({
  legendKey,
  title,
  children,
  className = '',
}: {
  legendKey?: string
  title?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`${ruleClasses('both')} py-4 ${className}`}>
      {(legendKey || title) && (
        <header className="mb-2 flex items-baseline gap-2">
          {legendKey && <span className="font-mono text-mono text-ink-3">{legendKey}</span>}
          {title && <h3 className="text-body-sm font-semibold text-ink">{title}</h3>}
        </header>
      )}
      <div className="text-body text-ink-2">{children}</div>
    </section>
  )
}
