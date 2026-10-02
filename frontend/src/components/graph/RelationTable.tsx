export default function RelationTable({ names }: { names: string[] }) {
  return (
    <div className="rounded-[6px] border border-ink-700 bg-ink-900 p-4">
      <h3 className="mb-3 text-label uppercase text-paper-mute">Relation types</h3>
      <ul className="space-y-1">
        {names.map((name) => (
          <li key={name} className="tnum font-mono text-mono text-paper-dim">
            {name}
          </li>
        ))}
      </ul>
    </div>
  )
}
