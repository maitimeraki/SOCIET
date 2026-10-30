import type { ReactNode } from 'react'
import { ruleClasses } from './Rule'

/**
 * §8.1 — the step from a page title to a section: the title, the optional lead beneath it, and
 * the rule that closes the block.
 *
 * The title is Fraunces at `text-title` in ink, the lead is one line of body copy, and the rule
 * is the kit's own — a hairline on the heading block itself, never a divider node between things.
 */
export type SectionHeadingProps = {
  /** The heading level: a page's section takes 2, a section's own sub-block takes 3. */
  level?: 2 | 3
  title: ReactNode
  lead?: ReactNode
  /** The rule that closes the heading. Off by default — a heading is not always a boundary. */
  rule?: boolean
  id?: string
  className?: string
}

const TITLE = 'font-display text-title text-ink'

export default function SectionHeading({
  level = 2,
  title,
  lead,
  rule = false,
  id,
  className = '',
}: SectionHeadingProps) {
  return (
    <div className={`${rule ? `${ruleClasses('bottom')} pb-6 ` : ''}${className}`}>
      {level === 3 ? (
        <h3 id={id} className={TITLE}>
          {title}
        </h3>
      ) : (
        <h2 id={id} className={TITLE}>
          {title}
        </h2>
      )}
      {lead ? <p className="mt-3 max-w-[56ch] text-body text-ink-2">{lead}</p> : null}
    </div>
  )
}
