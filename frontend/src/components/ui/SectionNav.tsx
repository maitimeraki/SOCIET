import { useRef } from 'react'
import type { KeyboardEvent } from 'react'
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
 *
 * A tablist is a real one (§14.4): each tab names its panel through `aria-controls` and is
 * labelled by the panel through `aria-labelledby`. Ids are derived from `idPrefix`, so the
 * caller's panels can name them without the kit inventing a second source of truth. Only the
 * active tab is in the tab order; Left/Right (Up/Down when vertical), Home and End move the
 * selection and the focus together — roving focus without a second active state.
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
  /** The prefix that ties each tab to its panel: `<prefix>-tab-<key>` and `<prefix>-panel-<key>`. */
  idPrefix?: string
}

/** The id of a destination's tab, derived from the strip's prefix. */
// eslint-disable-next-line react-refresh/only-export-components -- the id helpers are the tab/panel contract the caller and the kit share
export const sectionTabId = (idPrefix: string, key: string): string => `${idPrefix}-tab-${key}`

/** The id of a destination's panel, derived from the strip's prefix. */
// eslint-disable-next-line react-refresh/only-export-components -- the id helpers are the tab/panel contract the caller and the kit share
export const sectionPanelId = (idPrefix: string, key: string): string => `${idPrefix}-panel-${key}`

/**
 * The index a roving key moves to, or `null` when the key is not a roving key. Pure, so the key
 * map is testable without a DOM.
 */
// eslint-disable-next-line react-refresh/only-export-components -- the roving key map is the pure half of the keyboard behaviour, tested beside the strip
export function rovingIndex(key: string, index: number, count: number, vertical: boolean): number | null {
  if (count === 0 || index < 0) return null
  const forward = vertical ? 'ArrowDown' : 'ArrowRight'
  const backward = vertical ? 'ArrowUp' : 'ArrowLeft'
  if (key === forward) return (index + 1) % count
  if (key === backward) return (index - 1 + count) % count
  if (key === 'Home') return 0
  if (key === 'End') return count - 1
  return null
}

// 40 tall at the wireframe's measure (§14.4); 44 on a phone, where every control is a tap target (§14.5).
const ITEM = 'inline-flex min-h-10 shrink-0 items-center px-3 py-2 text-body transition-colors duration-state max-sm:min-h-11'

export default function SectionNav({
  items,
  active,
  onSelect,
  as = 'tabs',
  orientation = 'horizontal',
  className = '',
  idPrefix = 'section',
}: SectionNavProps) {
  const vertical = orientation === 'vertical'
  const refs = useRef<Array<HTMLButtonElement | null>>([])
  const resting = vertical ? `${ruleClasses('left')} text-ink-2 hover:text-ink` : `${ruleClasses('bottom')} text-ink-2 hover:text-ink`
  // The active item carries no rule of its own — the strip's rule breaks there — and the accent
  // band is drawn inside its edge.
  const selected = vertical ? 'text-ink shadow-accent-inset-left' : 'text-ink shadow-accent-inset'

  const select = (index: number) => {
    const item = items[index]
    if (!item) return
    onSelect?.(item.key)
    refs.current[index]?.focus()
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = items.findIndex((item) => item.key === active)
    const next = rovingIndex(event.key, index, items.length, vertical)
    if (next === null) return
    event.preventDefault()
    select(next)
  }

  const strip = items.map((item, index) => {
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
        ref={(element) => {
          refs.current[index] = element
        }}
        id={sectionTabId(idPrefix, item.key)}
        type="button"
        role="tab"
        aria-selected={isActive}
        aria-controls={sectionPanelId(idPrefix, item.key)}
        tabIndex={isActive ? 0 : -1}
        onClick={() => select(index)}
        className={classes}
      >
        {item.label}
      </button>
    )
  })

  // Horizontal items sit edge to edge, so their rules tile into one hairline that breaks only at
  // the active item. Vertical rules are drawn on the left, where a gap reads as separate rows.
  const layout = vertical ? 'flex flex-col items-stretch gap-1' : 'flex items-stretch'

  if (as === 'links') {
    return (
      <nav className={`${layout} ${className}`} aria-label="Section">
        {strip}
      </nav>
    )
  }
  return (
    <div
      role="tablist"
      aria-orientation={vertical ? 'vertical' : 'horizontal'}
      onKeyDown={onKeyDown}
      className={`${layout} ${className}`}
    >
      {strip}
    </div>
  )
}
