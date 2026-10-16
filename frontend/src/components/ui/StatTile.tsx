export default function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <div className="text-label uppercase text-ink-3">{label}</div>
      <div className="tnum mt-1 font-measurement text-mono-lg text-ink">{value}</div>
      {hint && <div className="mt-0.5 text-micro text-ink-3">{hint}</div>}
    </div>
  )
}
