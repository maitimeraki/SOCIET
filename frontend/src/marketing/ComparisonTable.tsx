import Table from '../components/ui/Table'
import { sections } from './copy'

/**
 * The differentiator, stated as a comparison of mechanisms — one answer from one voice against a
 * panel decision drawn from the owner's material. No third party is named and nothing is measured;
 * the foot says so, so the table is never read as a benchmark.
 */
export default function ComparisonTable() {
  const comparison = sections.comparison
  return (
    <section aria-labelledby="comparison-heading">
      <h2 id="comparison-heading" className="font-titling text-title text-ink">
        {comparison.heading}
      </h2>
      <p className="mt-2 max-w-[68ch] font-record text-[18px] leading-[28px] text-ink-2">{comparison.note}</p>

      {/* The ruled columns scroll horizontally rather than crushing under 640px (DSPEC §9). */}
      <div className="mt-4 overflow-x-auto">
        <Table
          head={
            <tr>
              <th scope="col" className="px-3 py-2 text-left font-titling text-ink-2">
                {comparison.approachColumn}
              </th>
              {comparison.columns.map((column) => (
                <th key={column} scope="col" className="px-3 py-2 text-left font-titling text-ink-2">
                  {column}
                </th>
              ))}
            </tr>
          }
          foot={
            <tr>
              <td colSpan={comparison.columns.length + 1} className="px-3 py-2 font-record text-[18px] leading-[28px] text-ink-2">
                {comparison.reconciliation}
              </td>
            </tr>
          }
        >
          {comparison.rows.map((row) => (
            <tr key={row.label}>
              <th scope="row" className="px-3 py-2 text-left align-top font-titling font-medium text-ink">
                {row.label}
              </th>
              {row.cells.map((cell, index) => (
                <td key={comparison.columns[index]} className="px-3 py-2 align-top">
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
