import type { ReactNode } from 'react'

/**
 * §8.2 / §8.4 — the caps label: 12px, semibold, 0.08em tracking, set in ink.
 *
 * `default` is the label on a light surface (ink-3). `quiet` is the label on a ground-2 fill,
 * where ink-3 falls under the contrast floor (DESIGN_SPEC §2.7) and ink-2 is the legible ink.
 *
 * `as` lets a site keep the element the label already was — a section's `h3`, a field's own
 * `<label>` — so adopting the primitive changes the class string and nothing else. `htmlFor` is
 * read only when the element is a `<label>`.
 */
export type LabelTone = 'default' | 'quiet'
export type LabelElement = 'span' | 'p' | 'h3' | 'label'

const TONE: Record<LabelTone, string> = {
  default: 'text-ink-3',
  quiet: 'text-ink-2',
}

export default function Label({
  children,
  tone = 'default',
  as = 'span',
  htmlFor,
  className = '',
}: {
  children: ReactNode
  tone?: LabelTone
  as?: LabelElement
  htmlFor?: string
  className?: string
}) {
  const classes = `text-label font-semibold uppercase tracking-[0.08em] ${TONE[tone]} ${className}`
  if (as === 'h3') return <h3 className={classes}>{children}</h3>
  if (as === 'p') return <p className={classes}>{children}</p>
  if (as === 'label')
    return (
      <label htmlFor={htmlFor} className={classes}>
        {children}
      </label>
    )
  return <span className={classes}>{children}</span>
}
