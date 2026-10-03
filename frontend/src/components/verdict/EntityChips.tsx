import Tag from '../ui/Tag'

export default function EntityChips({ supporting, opposing }: { supporting: string[]; opposing: string[] }) {
  if (supporting.length === 0 && opposing.length === 0) return <p className="text-body text-paper-mute">No entities recorded.</p>
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <div>
        <p className="mb-2 text-label uppercase text-paper-mute">For</p>
        <div className="flex flex-wrap gap-1.5">
          {supporting.map((entity) => (
            <Tag key={entity}>{entity}</Tag>
          ))}
        </div>
      </div>
      <div>
        <p className="mb-2 text-label uppercase text-paper-mute">Against</p>
        <div className="flex flex-wrap gap-1.5">
          {opposing.map((entity) => (
            <Tag key={entity}>{entity}</Tag>
          ))}
        </div>
      </div>
    </div>
  )
}
