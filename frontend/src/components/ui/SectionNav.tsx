import { ruleClasses } from './Rule'

/**
 * §14.1 — a nav strip across a section's destinations.
 *
 * The active destination reads as a **cut**: the strip's rule is drawn by the items themselves,
 * so the hairline stops where the active one begins, and the accent band takes its place. The
 * accent band is the `--shadow-accent-inset` token — an inset shadow, so it sits inside the
 * active item's own edge rather than under the strip.
 *
 * `as` chooses what the destinations are: `tabs` are buttons in a tablist, `links` are anchors
 * in a nav. `orientation` turns the strip on its side, and the rule follows it.
 */
export type SectionNavItem = {
  key: string
  label: string
  /** The link's destination — required when the strip is `links`. */
  href?: string
}

export type SectionNavProps = {
  items: SectionNavItem[]
  active: string
  onSelect?: (key: string) => void
  as?: 'tabs' | 'links'
  orientation?: 'horizontal' | 'vertical'
  className?: string
}

const ITEM = 'px-3 py-2 text-body transition-colors duration-state'

export default function SectionNav({
  items,
  active,
  onSelect,
  as = 'tabs',
  orientation = 'horizontal',
  className = '',
}: SectionNavProps) {
  const vertical = orientation === 'vertical'
  const resting = vertical ? `${ruleClasses('left')} text-ink-2 hover:text-ink` : `${ruleClasses('bottom')} text-ink-2 hover:text-ink`
  // The active item carries no rule of its own — the strip's rule breaks there — and the accent
  // band is drawn inside its edge.
  const selected = vertical ? 'text-ink shadow-accent-inset-left' : 'text-ink shadow-accent-inset'

  const strip = items.map((item) => {
    const isActive = item.key === active
    const classes = `${ITEM} ${isActive ? selected : resting}`
    if (as === 'links') {
      return (
        <a
          key={item.key}
          href={item.href ?? '#'}
          aria-current={isActive ? 'page' : undefined}
          className={classes}
        >
          {item.label}
        </a>
      )
    }
    return (
      <button
        key={item.key}
        type="button"
        role="tab"
        aria-selected={isActive}
        onClick={() => onSelect?.(item.key)}
        className={classes}
      >
        {item.label}
      </button>
    )
  })

  const layout = vertical ? 'flex flex-col items-stretch gap-1' : 'flex items-stretch gap-1'

  if (as === 'links') {
    return (
      <nav className={`${layout} ${className}`} aria-label="Section">
        {strip}
      </nav>
    )
  }
  return (
    <div role="tablist" className={`${layout} ${className}`}>
      {strip}
    </div>
  )
}
