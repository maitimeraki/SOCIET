import type { ReactNode } from 'react'

/**
 * §8.9 — a composed empty block: one dashed record rule, a short headline, one sentence, and
 * exactly one action. No sample data ever stands in for real material.
 *
 * `title` is optional so existing callers keep the single-sentence block; when a surface re-shells
 * its page it supplies the headline above the sentence.
 */
export default function EmptyState({
  icon,
  title,
  line,
  action,
}: {
  icon?: ReactNode
  title?: string
  line: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-md border border-dashed border-rule bg-paper px-5 py-8 text-center">
      {icon && <div className="text-ink-3">{icon}</div>}
      {title ? <p className="font-display text-heading text-ink">{title}</p> : null}
      <p className="max-w-[52ch] text-body text-ink-2">{line}</p>
      {action}
    </div>
  )
}
