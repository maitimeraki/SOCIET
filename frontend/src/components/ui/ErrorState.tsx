import type { ReactNode } from 'react'

export default function ErrorState({ title, detail, actions }: { title: string; detail?: string; actions?: ReactNode }) {
  return (
    <div className="rounded-[6px] border border-ink-4 bg-survey-paper-2 p-5">
      <p className="text-heading text-ink">{title}</p>
      {detail && <p className="mt-2 max-w-[60ch] text-body text-ink-2">{detail}</p>}
      {actions && <div className="mt-4 flex items-center gap-3">{actions}</div>}
    </div>
  )
}
