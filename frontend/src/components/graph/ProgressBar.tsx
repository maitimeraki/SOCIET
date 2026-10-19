export default function ProgressBar({ value, label }: { value: number; label?: string }) {
  const pct = Math.max(0, Math.min(1, value)) * 100
  return (
    <div>
      <div className="h-1 w-full overflow-hidden rounded-[4px] bg-ink-4">
        <div className="h-full rounded-[4px] bg-accent transition-[width] duration-200" style={{ width: `${pct}%` }} />
      </div>
      {label && <div className="tnum mt-2 font-measurement text-mono text-ink-3">{label}</div>}
    </div>
  )
}
