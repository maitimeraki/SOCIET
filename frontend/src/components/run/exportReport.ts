import { stanceWord } from '../ui/PositionMark'
import type { Position } from '../ui/PositionMark'
import { fmtPct, fmtScore } from '../../utils/format'

export interface ReportModel {
  question: string
  filed: string
  position: Position
  share: number | null
  caseAgainst: string
  reasoning: string[]
  whoHeldWhichView: { position: Position; names: string[] }[]
  sources: { document: string; reference: string }[]
  passes: { pass: string; negative: number; positive: number; ambivalent: number }[]
  panel: {
    name: string
    role: string
    position: Position
    confidence: number
    conviction: number
    receptivity: number
    turns: number
    weight: number
  }[]
  warnings: string[]
}

/** The share as the page and every export write it: stated when recorded, a dash when not. */
const shareText = (share: number | null): string => (share === null ? '—' : share.toFixed(2))

/**
 * §11.3 — one construction. The reading view and every export are serialized from the same
 * object, so there is no second writer to drift. The outcome and every position column speak the
 * customer's word (`stanceWord`); only `reportJson` keeps the enum, for machine consumers.
 */
export function reportMarkdown(report: ReportModel): string {
  const out: string[] = []
  out.push(`# ${report.question}`)
  out.push('')
  out.push(`**Filed ${report.filed}**`)
  out.push('')
  out.push(`**${stanceWord(report.position)} · ${shareText(report.share)} weighted share**`)
  out.push('')
  out.push('## The case against')
  out.push('')
  out.push(report.caseAgainst)
  out.push('')
  out.push('## The reasoning')
  out.push('')
  report.reasoning.forEach((paragraph) => {
    out.push(paragraph)
    out.push('')
  })
  out.push('## Who held which view')
  out.push('')
  report.whoHeldWhichView.forEach((row) => {
    out.push(`- **${stanceWord(row.position)}** — ${row.names.join(', ')}`)
  })
  out.push('')
  out.push('## The passes')
  out.push('')
  out.push('| Pass | Negative | Positive | Ambivalent |')
  out.push('|---|---|---|---|')
  report.passes.forEach((row) => {
    out.push(`| ${row.pass} | ${fmtPct(row.negative)} | ${fmtPct(row.positive)} | ${fmtPct(row.ambivalent)} |`)
  })
  out.push('')
  out.push('## The panel')
  out.push('')
  out.push('| Expert | Position | Turns | Conf. | Conv. | Recept. | Weight |')
  out.push('|---|---|---|---|---|---|---|')
  report.panel.forEach((row) => {
    out.push(
      `| ${row.name} (${row.role}) | ${stanceWord(row.position)} | ${row.turns} | ${fmtScore(row.confidence)} | ${fmtScore(row.conviction)} | ${fmtScore(row.receptivity)} | ${fmtScore(row.weight)} |`,
    )
  })
  out.push('')
  out.push('## Sources')
  out.push('')
  report.sources.forEach((source) => {
    out.push(`- ${source.document} — ${source.reference}`)
  })
  out.push('')
  if (report.warnings.length > 0) {
    out.push('## Warnings')
    out.push('')
    report.warnings.forEach((warning) => out.push(`- ${warning}`))
    out.push('')
  }
  return out.join('\n')
}

export function reportHtml(report: ReportModel): string {
  const escape = (value: string) =>
    value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const outcome = `${stanceWord(report.position)} · ${shareText(report.share)} weighted share`
  const passRows = report.passes
    .map(
      (row) =>
        `<tr><td>${escape(row.pass)}</td><td>${fmtPct(row.negative)}</td><td>${fmtPct(row.positive)}</td><td>${fmtPct(row.ambivalent)}</td></tr>`,
    )
    .join('')
  const panelRows = report.panel
    .map(
      (row) =>
        `<tr><td>${escape(row.name)} (${escape(row.role)})</td><td>${stanceWord(row.position)}</td><td>${row.turns}</td><td>${fmtScore(row.confidence)}</td><td>${fmtScore(row.conviction)}</td><td>${fmtScore(row.receptivity)}</td><td>${fmtScore(row.weight)}</td></tr>`,
    )
    .join('')
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${escape(report.question)}</title></head><body><h1>${escape(report.question)}</h1><p><strong>Filed ${escape(report.filed)}</strong></p><p><strong>${outcome}</strong></p><h2>The case against</h2><p>${escape(report.caseAgainst)}</p><h2>The reasoning</h2>${report.reasoning.map((paragraph) => `<p>${escape(paragraph)}</p>`).join('')}<h2>Who held which view</h2><ul>${report.whoHeldWhichView.map((row) => `<li><strong>${stanceWord(row.position)}</strong> — ${escape(row.names.join(', '))}</li>`).join('')}</ul><h2>The passes</h2><table><thead><tr><th scope="col">Pass</th><th scope="col">Negative</th><th scope="col">Positive</th><th scope="col">Ambivalent</th></tr></thead><tbody>${passRows}</tbody></table><h2>The panel</h2><table><thead><tr><th scope="col">Expert</th><th scope="col">Position</th><th scope="col">Turns</th><th scope="col">Conf.</th><th scope="col">Conv.</th><th scope="col">Recept.</th><th scope="col">Weight</th></tr></thead><tbody>${panelRows}</tbody></table><h2>Sources</h2><ul>${report.sources.map((source) => `<li>${escape(source.document)} — ${escape(source.reference)}</li>`).join('')}</ul>${report.warnings.length > 0 ? `<h2>Warnings</h2><ul>${report.warnings.map((warning) => `<li>${escape(warning)}</li>`).join('')}</ul>` : ''}</body></html>`
}

export function reportJson(report: ReportModel): string {
  return JSON.stringify(
    {
      meta: { question: report.question, filed: report.filed },
      // The enum stays here for machine consumers; every rendered form speaks `stanceWord`.
      outcome: { stance: report.position, share: report.share },
      report,
      // The same document as a readable string, serialized by the one markdown writer — not a copy.
      document: reportMarkdown(report),
    },
    null,
    2,
  )
}
