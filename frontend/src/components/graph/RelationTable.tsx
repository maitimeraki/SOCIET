import Label from '../ui/Label'
import { ruleClasses } from '../ui/Rule'

export default function RelationTable({ names }: { names: string[] }) {
  return (
    <div className={`${ruleClasses('top')} pt-4`}>
      <Label as="h3" className="mb-3">Relation types</Label>
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
