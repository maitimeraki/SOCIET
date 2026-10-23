import type { ReactNode } from 'react'

/**
 * §14.1 — the caps label: the name of a thing, set in the label face, in ink.
 *
 * `default` is the label on a light surface (ink-3). `quiet` is the label on a ground-2 fill,
 * where ink-3 falls under the contrast floor (DESIGN_SPEC §2.7) and ink-2 is the legible ink.
 */
export type LabelTone = 'default' | 'quiet'

const TONE: Record<LabelTone, string> = {
  default: 'text-ink-3',
  quiet: 'text-ink-2',
}

export default function Label({
  children,
  tone = 'default',
  className = '',
}: {
  children: ReactNode
  tone?: LabelTone
  className?: string
}) {
  return <span className={`text-label uppercase ${TONE[tone]} ${className}`}>{children}</span>
}
