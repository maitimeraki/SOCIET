import type { ReactNode } from 'react'

// §6 Tables — the traverse log: ruled columns, tabular figures, and a reconciliation line at the
// foot. Rules are --hairline (decorative dividers, §4.1) and the reconciliation line is the
// settled ink.
//
// THE COLUMN CONVENTION, in full — the frozen API cannot enforce it, so the caller applies it:
//   · any figure that is a measurement  → the mono face (`font-mono text-mono`)
//   · a LIVE value                      → `text-accent` (5.39:1 on the sheet, so legal as text)
//   · a SETTLED value                   → the body ink the <tbody> already sets
// The table itself guarantees only that the figures line up (`tnum`); it cannot know which column is
// which. See `common/RunTable.tsx` for the convention in use.
const RULED =
  '[&_td]:border-b [&_td]:border-hairline [&_td+_td]:border-l [&_td+_td]:border-l-hairline [&_th]:border-b [&_th]:border-hairline [&_th+_th]:border-l [&_th+_th]:border-l-hairline [&_tfoot_td]:border-t-2 [&_tfoot_td]:border-t-ink [&_tfoot_th]:border-t-2 [&_tfoot_th]:border-t-ink'

export default function Table({ head, children, foot, className = '' }: { head: ReactNode; children: ReactNode; foot?: ReactNode; className?: string }) {
  return (
    <table className={`tnum w-full border-collapse text-body ${RULED} ${className}`}>
      <thead className="sticky top-0 bg-sand text-label uppercase text-ink-2">{head}</thead>
      <tbody className="text-ink-2">{children}</tbody>
      {foot ? <tfoot>{foot}</tfoot> : null}
    </table>
  )
}
