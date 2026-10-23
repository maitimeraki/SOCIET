import type { ReactElement } from 'react'
import type { Stance } from '../../run/events'

/**
 * §14.1 — the position's **symbol + colour + word**, at any size. One owner: the app's
 * `StanceSymbol` (the glyph) and `StanceChip` (the word beside it) merge here, so a position
 * reads the same wherever it is drawn.
 *
 * House style rule 7: a position is never colour alone, and a position hue is never used as
 * text. The hue belongs to the drawn glyph; the word is always ink — the light ink on a light
 * surface, the map's ink on the dark one.
 *
 * The four positions are in the frozen order POSITIVE, NEUTRAL, AMBIVALENT, NEGATIVE (`STANCE_ORDER`
 * in `run/selectors.ts` is the one list of that order).
 *
 * The symbol is `aria-hidden`: it duplicates the word, which must always sit beside it. A mark
 * with no adjacent word is a bug.
 */
export type Position = Stance

/** The ground the mark is drawn on: a light surface, or the map's own dark surface. */
export type PositionGround = 'light' | 'map'

export type PositionMarkSize = 'sm' | 'md'

/** The light-ground ramp — the hue a position wears on the page. */
const LIGHT: Record<Position, string> = {
  POSITIVE: 'var(--color-pos-light)',
  NEUTRAL: 'var(--color-neu-light)',
  AMBIVALENT: 'var(--color-amb-light)',
  NEGATIVE: 'var(--color-neg-light)',
}

/** The map-ground ramp — the hue the same position wears on the map. */
const MAP: Record<Position, string> = {
  POSITIVE: 'var(--color-pos)',
  NEUTRAL: 'var(--color-neu)',
  AMBIVALENT: 'var(--color-amb)',
  NEGATIVE: 'var(--color-neg)',
}

/**
 * Every glyph is authored geometry — a station triangle, a graticule square, a dashed circle, a
 * cross-hatch — not a unicode character standing in for an icon, and not a picture. Form is what
 * carries the meaning; the hue is the map legend's own convention and is a symbol colour only.
 */
const GLYPH: Record<Position, (color: string) => ReactElement> = {
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

/**
 * The glyph alone — for a legend, where the legend's own label is the word beside it. The mark
 * proper is `PositionMark` below; this is the same drawn form without the word.
 */
export function PositionGlyph({
  position,
  size = 14,
  ground,
}: {
  position: Position
  size?: number
  ground: PositionGround
}) {
  const color = ground === 'map' ? MAP[position] : LIGHT[position]
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      {GLYPH[position](color)}
    </svg>
  )
}

export default function PositionMark({
  position,
  size = 'md',
  ground,
}: {
  position: Position
  size?: PositionMarkSize
  ground: PositionGround
}) {
  const small = size === 'sm'
  const word = ground === 'map' ? 'text-map-ink' : 'text-ink'
  return (
    <span className={`inline-flex items-center gap-1.5 ${word} ${small ? 'text-micro' : 'text-label'}`}>
      <PositionGlyph position={position} size={small ? 11 : 13} ground={ground} />
      {position}
    </span>
  )
}
