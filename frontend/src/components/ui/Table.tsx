import type { ReactNode } from 'react'

export default function Table({ head, children, className = '' }: { head: ReactNode; children: ReactNode; className?: string }) {
  return (
    <table className={`w-full border-collapse text-body ${className}`}>
      <thead className="sticky top-0 bg-ink-900 text-label uppercase text-paper-mute">{head}</thead>
      <tbody className="text-paper-dim">{children}</tbody>
    </table>
  )
}
