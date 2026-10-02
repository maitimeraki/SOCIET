export default function SchemaCard({ title, names }: { title: string; names: string[] }) {
  return (
    <div className="rounded-[6px] border border-ink-700 bg-ink-900 p-4">
      <h3 className="mb-3 text-label uppercase text-paper-mute">{title}</h3>
      <div className="flex flex-wrap gap-1.5">
        {names.map((name) => (
          <span key={name} className="rounded-[4px] border border-ink-700 bg-ink-800 px-1.5 py-0.5 text-micro text-paper-dim">
            {name}
          </span>
        ))}
      </div>
    </div>
  )
}
