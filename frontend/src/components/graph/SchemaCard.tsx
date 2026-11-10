import Label from '../ui/Label'
import { ruleClasses } from '../ui/Rule'

export default function SchemaCard({ title, names }: { title: string; names: string[] }) {
  return (
    <div className={`${ruleClasses('top')} pt-4`}>
      <Label as="h3" className="mb-3">{title}</Label>
      <div className="flex flex-wrap gap-1.5">
        {names.map((name) => (
          <span key={name} className="rounded-xs border border-hairline bg-sand px-1.5 py-0.5 text-micro text-ink-2">
            {name}
          </span>
        ))}
      </div>
    </div>
  )
}
