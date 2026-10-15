import Table from '../components/ui/Table'
import { sections } from './copy'

/**
 * The differentiator (plan §3.1 §5, DSPEC §7.1). Builds on `ui/Table.tsx` — the traverse log's ruled
 * columns — and states truthful differences only: no invented competitor capability, no benchmark.
 *
 * `ui/Table.tsx` had zero consumers since Task 14a; this is its first, so the ruled-column convention
 * (hairline rules, tabular figures, a reconciliation line at the foot) is exercised for real. Every
 * cell is settled prose, so it takes the `<tbody>` ink the primitive already sets — no live figures,
 * no measurements, and so no `text-datum` and no mono.
 */
export default function ComparisonTable() {
  const { heading, note, approachColumn, columns, rows, reconciliation } = sections.comparison
  return (
    <section>
      <h2 className="text-title text-ink">{heading}</h2>
      <p className="mt-2 max-w-[68ch] text-body-lg text-ink-2">{note}</p>

      {/* The ruled columns scroll horizontally rather than crushing under 640px (DSPEC §9). */}
      <div className="mt-4 overflow-x-auto">
        <Table
          head={
            <tr>
              <th scope="col" className="px-3 py-2 text-left">
                {approachColumn}
              </th>
              {columns.map((column) => (
                <th key={column} scope="col" className="px-3 py-2 text-left">
                  {column}
                </th>
              ))}
            </tr>
          }
          foot={
            <tr>
              <td colSpan={columns.length + 1} className="px-3 py-2 text-ink-3">
                {reconciliation}
              </td>
            </tr>
          }
        >
          {rows.map((row) => (
            <tr key={row.label}>
              <th scope="row" className="px-3 py-2 text-left align-top font-medium text-ink">
                {row.label}
              </th>
              {row.cells.map((cell, index) => (
                <td key={columns[index]} className="px-3 py-2 align-top">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </Table>
      </div>
    </section>
  )
}
