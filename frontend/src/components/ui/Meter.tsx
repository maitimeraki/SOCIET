/**
 * §8.6 — one measured share, **drawn**, with its figure beside it. The track is a 6px sand rule,
 * the fill is the accent, and the figure is set in the mono, tabular face so a number never
 * competes with prose.
 *
 * `tone` chooses the fill: `accent` is the live accent, `ink` is the quiet fill for a share
 * already stated in ink beside it. `width` chooses the track's length: `sm` is the measure beside
 * a label, `full` is the share across the width of a sheet.
 */
export type MeterTone = 'accent' | 'ink'
export type MeterWidth = 'sm' | 'full'

export default function Meter({
  value,
  max = 1,
  label,
  display,
  tone = 'accent',
  width = 'sm',
  className = '',
}: {
  /** The share drawn; `null` is an unrecorded share — an empty track, never a zero-width fill. */
  value: number | null
  max?: number
  label: string
  display: string
  tone?: MeterTone
  width?: MeterWidth
  className?: string
}) {
  const pct = value === null || max <= 0 ? null : Math.max(0, Math.min(1, value / max)) * 100
  const fill = tone === 'accent' ? 'bg-accent' : 'bg-ink'
  const full = width === 'full'
  return (
    <span className={`flex items-center gap-2 ${full ? 'w-full' : ''} ${className}`} title={`${label}: ${display}`}>
      <span className="w-9 text-micro text-ink-3">{label}</span>
      <span className={`h-1.5 ${full ? 'flex-1' : 'w-14'} rounded-xs bg-sand`}>
        {pct === null ? null : <span className={`block h-full rounded-xs ${fill}`} style={{ width: `${pct}%` }} />}
      </span>
      <span className="tnum font-mono text-micro text-ink-2">{display}</span>
    </span>
  )
}
