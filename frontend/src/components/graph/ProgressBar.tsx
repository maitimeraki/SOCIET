export default function ProgressBar({ value, label }: { value: number; label?: string }) {
  const pct = Math.max(0, Math.min(1, value)) * 100
  return (
    <div>
      <div className="h-1 w-full overflow-hidden rounded-xs bg-ink-4">
        <div
          className="h-full w-full origin-left rounded-xs bg-accent transition-transform duration-layout"
          style={{ transform: `scaleX(${pct / 100})` }}
        />
      </div>
      {label && <div className="tnum mt-2 font-measurement text-mono text-ink-3">{label}</div>}
    </div>
  )
}
