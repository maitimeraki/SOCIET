import Label from './Label'

/**
 * §14.1 — a measured number: mono, tabular, and never competing with prose. House style rule 6 —
 * a figure is always mono and tabular, and a number never competes with a sentence.
 *
 * `size` chooses the figure's weight on the page: `mono` is the figure at card scale (20/26),
 * `numeral` is the figure at panel scale (56/56) — the one that carries a surface's claim.
 *
 * The label is the kit's own `Label`, so the caps label has one owner (`ui/Label.tsx`) and a
 * change to it reaches here too.
 */
export type FigureSize = 'mono' | 'numeral'

export default function Figure({
  value,
  size = 'mono',
  label,
  hint,
  className = '',
}: {
  value: string
  size?: FigureSize
  label?: string
  hint?: string
  className?: string
}) {
  return (
    <div className={className}>
      {label ? <Label className="block">{label}</Label> : null}
      <div
        className={[
          'tnum',
          label ? 'mt-1' : '',
          'font-mono',
          size === 'numeral' ? 'text-numeral' : 'text-mono text-[20px] leading-[26px]',
          'text-ink',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        {value}
      </div>
      {hint ? <div className="mt-0.5 text-micro text-ink-3">{hint}</div> : null}
    </div>
  )
}
