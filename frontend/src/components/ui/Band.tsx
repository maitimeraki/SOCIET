import type { ReactNode } from 'react'
import './bands.css'

/**
 * §14.1 — the band vocabulary. A band is a **flat fill** on a named surface, and each tone means
 * exactly one thing: the page, a step down from it, the mechanism (sky), the caution (warm), the
 * answer (plum), or the work (the map's own dark surface).
 *
 * The class name follows the tone, so a surface reads the same wherever it is used: the
 * homepage's plum band and the dashboard's plum band are one band, not two look-alikes.
 *
 * The fills live in `bands.css`, and every one of them is a token — a band names a surface, it
 * never carries a hex (house style rule 1).
 */
export type BandTone = 'page' | 'band' | 'sky' | 'warm' | 'plum' | 'dark'

export type BandProps = {
  tone?: BandTone
  dense?: boolean
  as?: 'section' | 'div'
  id?: string
  'aria-labelledby'?: string
  'aria-label'?: string
  className?: string
  children?: ReactNode
}

export default function Band({
  tone = 'page',
  dense = false,
  as = 'section',
  id,
  'aria-labelledby': labelledBy,
  'aria-label': label,
  className = '',
  children,
}: BandProps) {
  const classes = ['band', `band--${tone}`, dense ? 'band--dense' : '', className]
    .filter(Boolean)
    .join(' ')
  // The class comes first because that is the shape §14.1 and the brief specify:
  // `class="band band--sky" id="…"`.
  const props = { className: classes, id, 'aria-labelledby': labelledBy, 'aria-label': label }

  return as === 'div' ? <div {...props}>{children}</div> : <section {...props}>{children}</section>
}
