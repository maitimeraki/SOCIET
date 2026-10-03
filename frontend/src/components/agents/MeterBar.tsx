export default function MeterBar({
  label,
  value,
  max = 1,
  display,
}: {
  label: string
  value: number
  max?: number
  display: string
}) {
  const pct = max > 0 ? Math.max(0, Math.min(1, value / max)) * 100 : 0
  return (
    <span className="flex items-center gap-2" title={`${label}: ${display}`}>
      <span className="w-9 text-micro text-paper-mute">{label}</span>
      <span className="h-1 w-14 rounded-[4px] bg-ink-700">
        <span className="block h-full rounded-[4px] bg-accent" style={{ width: `${pct}%` }} />
      </span>
      <span className="tnum font-mono text-micro text-paper-dim">{display}</span>
    </span>
  )
}
