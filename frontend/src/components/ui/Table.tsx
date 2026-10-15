import type { ReactNode } from 'react'

export default function Table({ head, children, className = '' }: { head: ReactNode; children: ReactNode; className?: string }) {
  return (
    <table className={`w-full border-collapse text-body ${className}`}>
      <thead className="sticky top-0 bg-survey-paper-2 text-label uppercase text-ink-3">{head}</thead>
      <tbody className="text-ink-2">{children}</tbody>
    </table>
  )
}
