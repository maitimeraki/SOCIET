import type { ReactNode } from 'react'

export default function EmptyState({ icon, line, action }: { icon?: ReactNode; line: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-[6px] border border-dashed border-ink-4 px-6 py-10 text-center">
      {icon && <div className="text-ink-3">{icon}</div>}
      <p className="max-w-[52ch] text-body text-ink-2">{line}</p>
      {action}
    </div>
  )
}
