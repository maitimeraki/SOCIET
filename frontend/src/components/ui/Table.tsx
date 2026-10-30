import type { ReactNode } from 'react'

// §8.8 Tables — ruled, no zebra, no vertical rules. The header is 12px caps in ink-3; rows are
// 52px and closed by one record rule; hover is the evergreen wash.
//
// THE COLUMN CONVENTION, in full — the frozen API cannot enforce it, so the caller applies it:
//   · a numeric column's cells carry `className="num"` → mono, tabular, right-aligned
//   · a LIVE value                      → `text-accent` (legal as text on paper)
//   · a SETTLED value                   → the body ink the <tbody> already sets
const RULED =
  '[&_th]:border-b [&_th]:border-rule [&_td]:h-[52px] [&_td]:border-b [&_td]:border-rule [&_tbody_tr:hover]:bg-accent-soft [&_.num]:text-right [&_.num]:font-mono [&_.num]:tnum [&_tfoot_td]:border-t-2 [&_tfoot_td]:border-t-ink [&_tfoot_th]:border-t-2 [&_tfoot_th]:border-t-ink'

export default function Table({ head, children, foot, className = '' }: { head: ReactNode; children: ReactNode; foot?: ReactNode; className?: string }) {
  return (
    <table className={`tnum w-full border-collapse text-body-sm ${RULED} ${className}`}>
      <thead className="text-label uppercase text-ink-3">{head}</thead>
      <tbody className="text-ink-2">{children}</tbody>
      {foot ? <tfoot>{foot}</tfoot> : null}
    </table>
  )
}
