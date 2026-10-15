import type { ReactNode } from 'react'

export default function Tag({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-[4px] border border-ink-4 bg-survey-paper-2 px-1.5 py-0.5 text-micro text-ink-2">
      {children}
    </span>
  )
}
