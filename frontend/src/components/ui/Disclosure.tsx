import type { ReactNode } from 'react'
import { ruleClasses } from './Rule'

/**
 * §8.3 — a native `<details>` on one record rule, with no card. The platform owns the open state;
 * the marker is a mono `+` / `−` in ink-3, not the browser's triangle.
 */
export default function Disclosure({
  summary,
  children,
  defaultOpen = false,
}: {
  summary: ReactNode
  children: ReactNode
  defaultOpen?: boolean
}) {
  return (
    <details className={`group ${ruleClasses('top')} py-5`} open={defaultOpen || undefined}>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-6 text-body font-semibold text-ink [&::-webkit-details-marker]:hidden">
        {summary}
        <span aria-hidden="true" className="font-mono text-ink-3">
          <span className="group-open:hidden">+</span>
          <span className="hidden group-open:inline">−</span>
        </span>
      </summary>
      <div className="pt-3 text-body-sm text-ink-2">{children}</div>
    </details>
  )
}
