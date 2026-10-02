export default function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <div className="text-label uppercase text-paper-mute">{label}</div>
      <div className="tnum mt-1 font-mono text-mono-lg text-paper">{value}</div>
      {hint && <div className="mt-0.5 text-micro text-paper-mute">{hint}</div>}
    </div>
  )
}
