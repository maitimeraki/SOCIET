import type { ReactNode } from 'react'

/**
 * §8.9 — a composed empty block: one dashed record rule, one sentence, and exactly one action.
 * No sample data ever stands in for real material.
 */
export default function EmptyState({ icon, line, action }: { icon?: ReactNode; line: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-md border border-dashed border-rule bg-paper px-5 py-8 text-center">
      {icon && <div className="text-ink-3">{icon}</div>}
      <p className="max-w-[52ch] text-body text-ink-2">{line}</p>
      {action}
    </div>
  )
}
