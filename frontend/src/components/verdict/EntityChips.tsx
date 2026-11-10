import Chip from '../ui/Chip'
import Label from '../ui/Label'

export default function EntityChips({ supporting, opposing }: { supporting: string[]; opposing: string[] }) {
  if (supporting.length === 0 && opposing.length === 0) return <p className="text-body text-ink-3">No entities recorded.</p>
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <div>
        <Label as="p" className="mb-2">For</Label>
        <div className="flex flex-wrap gap-1.5">
          {supporting.map((entity) => (
            <Chip key={entity}>{entity}</Chip>
          ))}
        </div>
      </div>
      <div>
        <Label as="p" className="mb-2">Against</Label>
        <div className="flex flex-wrap gap-1.5">
          {opposing.map((entity) => (
            <Chip key={entity}>{entity}</Chip>
          ))}
        </div>
      </div>
    </div>
  )
}
