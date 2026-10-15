/**
 * §6 The fix — the verdict mark.
 *
 * ONE mark owns the word "verdict": an ink ring with a brass centre and the vermilion plotted point,
 * always accompanied by the confidence figure in mono. DSPEC §6 is explicit — *nothing else may use
 * it* — so it is the product's single "this is the finding" signal, and a second use anywhere dilutes
 * it to a decoration.
 *
 * **IMPORT ONLY FROM A VERDICT SURFACE (Tasks 16 / 16B).** The component is intentionally not
 * re-exported from any barrel, so every import site is a deliberate one.
 *
 * The ring is drawn in `currentColor` rather than a hardcoded ink, so the mark is not married to the
 * light sheet: on the plotting table (`--plot-ground`) `--ink` measures 1.04:1 and disappears — a
 * caller there passes `className="text-ink-4"` (8.46:1). `--brass` (7.14:1) and the vermilion point
 * (3.38:1) clear the mark floor on either ground, so only the ring switches.
 */
export default function FixMark({
  confidence,
  size = 40,
  className = '',
}: {
  /** The weighted confidence, 0–1. `null` renders the em-dash placeholder rather than a fake zero. */
  confidence: number | null
  /** The ring's box in px. The figure scales independently, so the mark stays readable at any size. */
  size?: number
  /** Ground override — see the note above about the plotting table. */
  className?: string
}) {
  return (
    <span className={`inline-flex items-center gap-3 text-ink ${className}`}>
      <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" focusable="false" className="shrink-0">
        {/* the fix circle — an ink ring */}
        <circle cx="20" cy="20" r="15" fill="none" stroke="currentColor" strokeWidth="1.5" />
        {/* the brass centre — the instrument's own mark */}
        <circle cx="20" cy="20" r="5" fill="var(--color-brass)" />
        {/* the plotted point — it blooms once and settles (§5, the `fix` move) */}
        <circle
          cx="30"
          cy="10"
          r="3.4"
          fill="var(--color-route)"
          className="fix"
          style={{ transformOrigin: '30px 10px' }}
        />
      </svg>
      <span className="tnum font-measurement text-mono-lg">
        <span className="sr-only">weighted confidence </span>
        {confidence === null ? '—' : confidence.toFixed(2)}
      </span>
    </span>
  )
}
