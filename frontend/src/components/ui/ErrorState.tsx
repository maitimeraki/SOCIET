import type { ReactNode } from 'react'

export default function ErrorState({ title, detail, actions }: { title: string; detail?: string; actions?: ReactNode }) {
  return (
    <div className="rounded-[6px] border border-ink-600 bg-ink-900 p-5">
      <p className="text-heading text-paper">{title}</p>
      {detail && <p className="mt-2 max-w-[60ch] text-body text-paper-dim">{detail}</p>}
      {actions && <div className="mt-4 flex items-center gap-3">{actions}</div>}
    </div>
  )
}
