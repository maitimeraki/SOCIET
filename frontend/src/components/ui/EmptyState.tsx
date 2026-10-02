import type { ReactNode } from 'react'

export default function EmptyState({ icon, line, action }: { icon?: ReactNode; line: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-[6px] border border-dashed border-ink-600 px-6 py-10 text-center">
      {icon && <div className="text-paper-mute">{icon}</div>}
      <p className="max-w-[52ch] text-body text-paper-dim">{line}</p>
      {action}
    </div>
  )
}
