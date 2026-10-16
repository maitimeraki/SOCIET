import type { Stance } from '../../run/events'
import StanceSymbol from './StanceSymbol'

/**
 * §6/§9 The legend law. A stance renders as **symbol + colour + word** at every size: the hue belongs
 * to the drawn glyph, and the word is always ink — §3.1 R29/F3 makes the four stance hues symbol
 * colours only (pos 4.44:1 · neu 4.37:1 · amb 2.93:1 · neg 4.67:1 on the sheet), so none of them may
 * be text. A colour with no visible symbol fails accessibility and is banned (DSPEC §9), so there is
 * no colour-only variant of this component and no prop that hides the word.
 *
 * The chip is deliberately neither a pill nor a box. The incumbent's `--ink-4` outline measured
 * 1.88:1 against its own fill (addendum §7) and is gone; an enclosed bordered box is the one shape
 * the Survey refuses (§6 — cards are absent by law), so the stance reads from the glyph and the word
 * and nothing else.
 */
export default function StanceChip({ stance, size = 'md' }: { stance: Stance; size?: 'sm' | 'md' }) {
  const small = size === 'sm'
  return (
    <span className={`inline-flex items-center gap-1.5 text-ink ${small ? 'text-micro' : 'text-label'}`}>
      <StanceSymbol stance={stance} size={small ? 11 : 13} />
      {stance}
    </span>
  )
}
