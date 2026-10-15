import type { ReactNode } from 'react'

// §6 Tables — the traverse log: ruled columns, tabular figures, and a reconciliation line at the
// foot. Rules are --ink-4 (decorative hairlines, addendum §1) and the reconciliation line is the
// settled ink. Live values take --datum (5.39:1 on the sheet, so it is legal as text); settled
// values keep the body ink. Measurement cells are the caller's to set in the mono face
// (`font-measurement text-mono`) — the table only guarantees the figures line up.
const RULED =
  '[&_td]:border-b [&_td]:border-ink-4 [&_td+_td]:border-l [&_td+_td]:border-l-ink-4 [&_th]:border-b [&_th]:border-ink-4 [&_th+_th]:border-l [&_th+_th]:border-l-ink-4 [&_tfoot_td]:border-t-2 [&_tfoot_td]:border-t-ink [&_tfoot_th]:border-t-2 [&_tfoot_th]:border-t-ink'

export default function Table({ head, children, className = '' }: { head: ReactNode; children: ReactNode; className?: string }) {
  return (
    <table className={`tnum w-full border-collapse text-body ${RULED} ${className}`}>
      <thead className="sticky top-0 bg-survey-paper-2 text-label uppercase text-ink-3">{head}</thead>
      <tbody className="text-ink-2">{children}</tbody>
    </table>
  )
}
