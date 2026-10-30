import type { Stance } from '../../run/events'

/**
 * §4.6 — the position's **symbol + word + colour**, at any size. One owner, so a position reads
 * the same wherever it is drawn.
 *
 * Colour is never the only signal and a position hue is never used as text: the hue belongs to the
 * drawn symbol, the word is always ink — the light ink on a light surface, the map's ink on pine.
 *
 * The four positions are in the frozen order POSITIVE, NEUTRAL, AMBIVALENT, NEGATIVE
 * (`STANCE_ORDER` in `run/selectors.ts` is the one list of that order).
 */
export type Position = Stance

export type PositionGround = 'light' | 'map'
export type PositionMarkSize = 'sm' | 'md'

/** The word each position is written in. The enum is uppercase; the customer never sees it. */
const WORD: Record<Position, string> = {
  POSITIVE: 'Positive',
  NEUTRAL: 'Neutral',
  AMBIVALENT: 'Ambivalent',
  NEGATIVE: 'Negative',
}

/** The symbol each position is drawn with. */
const SYMBOL: Record<Position, string> = {
  POSITIVE: '▲',
  NEUTRAL: '●',
  AMBIVALENT: '◐',
  NEGATIVE: '▼',
}

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

/** The glyph alone — for a legend, where the legend's own label is the word beside it. */
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
    <span
      aria-hidden="true"
      style={{ color, fontSize: size, lineHeight: 1 }}
      className="inline-block leading-none"
    >
      {SYMBOL[position]}
    </span>
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
      {WORD[position]}
    </span>
  )
}
