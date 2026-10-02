import type { ReactNode } from 'react'

export default function Tag({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-[4px] border border-ink-700 bg-ink-800 px-1.5 py-0.5 text-micro text-paper-dim">
      {children}
    </span>
  )
}
