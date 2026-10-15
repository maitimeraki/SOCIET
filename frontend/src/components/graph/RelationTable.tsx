export default function RelationTable({ names }: { names: string[] }) {
  return (
    <div className="rounded-[6px] border border-ink-4 bg-survey-paper-2 p-4">
      <h3 className="mb-3 text-label uppercase text-ink-3">Relation types</h3>
      <ul className="space-y-1">
        {names.map((name) => (
          <li key={name} className="tnum font-measurement text-mono text-ink-2">
            {name}
          </li>
        ))}
      </ul>
    </div>
  )
}
