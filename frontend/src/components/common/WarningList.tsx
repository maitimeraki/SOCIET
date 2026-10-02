import { Warning } from '@phosphor-icons/react'

export default function WarningList({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) return null
  return (
    <ul className="space-y-2">
      {warnings.map((warning) => (
        <li key={warning} className="flex items-start gap-2 text-body text-paper-dim">
          <Warning size={16} className="mt-0.5 shrink-0 text-brass" aria-hidden="true" />
          <span>{warning}</span>
        </li>
      ))}
    </ul>
  )
}
