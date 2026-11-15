import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ReportDocument from './ReportDocument'
import { reportMarkdown, reportJson, reportHtml } from './exportReport'

const REPORT = {
  question: 'Should Ridgeline Coffee open a second location on Mill Street?',
  filed: '22 Oct 2026',
  position: 'NEGATIVE' as const,
  share: 0.82,
  caseAgainst: 'If the grease-trap upgrade lands on time, the Mill Street economics hold.',
  reasoning: ['The panel divided on timing, not on the location.'],
  whoHeldWhichView: [{ position: 'NEGATIVE' as const, names: ['Market analyst'] }],
  passes: [{ pass: 'P1', negative: 0.61, positive: 0.28, abstain: 0.11 }],
  panel: [{ name: 'Tom Okafor', role: 'local regulator', position: 'NEGATIVE' as const, confidence: 0.94, strength: 0.95, turns: 4 }],
  warnings: ['The demand study is a proxy.'],
}

describe('the filed report', () => {
  it('carries the case against and the share', () => {
    const html = renderToStaticMarkup(<ReportDocument report={REPORT} />)
    expect(html).toContain('The case against')
    expect(html).toContain('0.82')
  })

  it('exports the same document as markdown, html and json', () => {
    expect(reportMarkdown(REPORT)).toContain('The case against')
    expect(reportMarkdown(REPORT)).toContain('0.82')
    expect(reportHtml(REPORT)).toContain('The case against')
    expect(reportJson(REPORT)).toContain('The case against')
    expect(JSON.parse(reportJson(REPORT)).outcome.share).toBe(0.82)
  })
})
