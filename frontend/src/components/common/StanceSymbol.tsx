import type { ReactElement } from 'react'
import type { Stance } from '../../run/events'

/**
 * §6/§9 The legend law's glyphs — one drawn form per stance, so stance survives CVD, greyscale and
 * a monochrome print. Form is what carries the meaning; the hue is the map legend's own convention
 * (vegetation / unwooded / marsh / route) and is a *symbol* colour only, never text (§3.1 R29/F3).
 *
 * Every glyph is authored geometry — a station triangle, a graticule square, a dashed circle, a
 * cross-hatch — not a unicode character standing in for an icon, and not a picture.
 *
 * The symbol is `aria-hidden`: it duplicates the stance WORD, which must always sit beside it (the
 * legend law is symbol + colour + word at every size). A symbol with no adjacent word is a bug.
 */
const DEFAULT_COLOR: Record<Stance, string> = {
  POSITIVE: 'var(--color-pos-light)',
  NEUTRAL: 'var(--color-neu-light)',
  AMBIVALENT: 'var(--color-amb-light)',
  NEGATIVE: 'var(--color-neg-light)',
}

const GLYPH: Record<Stance, (color: string) => ReactElement> = {
  // POSITIVE — filled green station triangle (a triangulation station, the survey's own mark).
  POSITIVE: (color) => <polygon points="8,1.4 14.6,13.6 1.4,13.6" fill={color} />,
  // NEUTRAL — slate graticule square: a station square ruled through with the grid it is read on.
  NEUTRAL: (color) => (
    <g fill="none" stroke={color} strokeWidth="1.5">
      <rect x="2.2" y="2.2" width="11.6" height="11.6" />
      <path d="M2.2 8h11.6M8 2.2v11.6" />
    </g>
  ),
  // AMBIVALENT — amber dashed circle: an unresolved reading, drawn as a broken line.
  AMBIVALENT: (color) => (
    <circle
      cx="8"
      cy="8"
      r="5.6"
      fill="none"
      stroke={color}
      strokeWidth="1.6"
      strokeDasharray="2.6 2.1"
    />
  ),
  // NEGATIVE — vermilion cross-hatch: the ruled-out mark.
  NEGATIVE: (color) => (
    <path
      d="M2.4 2.4 13.6 13.6M13.6 2.4 2.4 13.6"
      fill="none"
      stroke={color}
      strokeWidth="1.8"
      strokeLinecap="round"
    />
  ),
}

/** `color` overrides the light-ground token — the map legend draws the same form at its row's hue. */
export default function StanceSymbol({ stance, size = 14, color }: { stance: Stance; size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      {GLYPH[stance](color ?? DEFAULT_COLOR[stance])}
    </svg>
  )
}
