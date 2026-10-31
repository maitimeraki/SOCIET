import VerdictSheet from '../ui/VerdictSheet'
import Table from '../ui/Table'
import Label from '../ui/Label'
import PositionMark from '../ui/PositionMark'
import { fmtPct, fmtScore } from '../../utils/format'
import type { ReportModel } from './exportReport'

/**
 * §12.8 — the filed report is the document itself: the verdict sheet, then the two matrices the
 * record supports. It reads from the same `ReportModel` every export is serialized from, so the
 * page and the files cannot disagree.
 */
export default function ReportDocument({ report }: { report: ReportModel }) {
  return (
    <div className="max-w-[760px] space-y-6">
      <VerdictSheet
        question={report.question}
        filed={report.filed}
        position={report.position}
        share={report.share}
        caseAgainst={report.caseAgainst}
        reasoning={report.reasoning}
        whoHeldWhichView={report.whoHeldWhichView}
        sources={report.sources}
      />

      <section className="rounded-xl bg-paper p-12 shadow-sheet">
        <Label as="h3">The passes</Label>
        <Table
          className="mt-4"
          head={
            <tr>
              <th scope="col">Pass</th>
              <th scope="col" className="num">
                Negative
              </th>
              <th scope="col" className="num">
                Positive
              </th>
              <th scope="col" className="num">
                Ambivalent
              </th>
            </tr>
          }
        >
          {report.passes.map((row) => (
            <tr key={row.pass}>
              <td>{row.pass}</td>
              <td className="num">{fmtPct(row.negative)}</td>
              <td className="num">{fmtPct(row.positive)}</td>
              <td className="num">{fmtPct(row.ambivalent)}</td>
            </tr>
          ))}
        </Table>

        <Label as="h3" className="mt-10 block">
          The panel
        </Label>
        <Table
          className="mt-4"
          head={
            <tr>
              <th scope="col">Expert</th>
              <th scope="col">Position</th>
              <th scope="col" className="num">
                Turns
              </th>
              <th scope="col" className="num">
                Conf.
              </th>
              <th scope="col" className="num">
                Conv.
              </th>
              <th scope="col" className="num">
                Recept.
              </th>
              <th scope="col" className="num">
                Weight
              </th>
            </tr>
          }
        >
          {report.panel.map((row) => (
            <tr key={row.name}>
              <td>
                {row.name} <span className="text-ink-3">({row.role})</span>
              </td>
              <td>
                <PositionMark position={row.position} size="sm" ground="light" />
              </td>
              <td className="num">{row.turns}</td>
              <td className="num">{fmtScore(row.confidence)}</td>
              <td className="num">{fmtScore(row.conviction)}</td>
              <td className="num">{fmtScore(row.receptivity)}</td>
              <td className="num">{fmtScore(row.weight)}</td>
            </tr>
          ))}
        </Table>

        {report.warnings.length > 0 ? (
          <section className="mt-10 border-t border-rule pt-6">
            <Label as="h3">Warnings</Label>
            <ul className="mt-3 space-y-1 font-ui text-body-sm text-ink-2">
              {report.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </section>
        ) : null}
      </section>
    </div>
  )
}
