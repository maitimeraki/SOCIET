export default function SchemaCard({ title, names }: { title: string; names: string[] }) {
  return (
    <div className="rounded-[6px] border border-ink-4 bg-survey-paper-2 p-4">
      <h3 className="mb-3 text-label uppercase text-ink-3">{title}</h3>
      <div className="flex flex-wrap gap-1.5">
        {names.map((name) => (
          <span key={name} className="rounded-[4px] border border-ink-4 bg-survey-paper-2 px-1.5 py-0.5 text-micro text-ink-2">
            {name}
          </span>
        ))}
      </div>
    </div>
  )
}
