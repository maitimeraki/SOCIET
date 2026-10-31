import { describe, expect, it } from 'vitest'
import { reportHtml, reportJson, reportMarkdown } from './exportReport'
import type { ReportModel } from './exportReport'

const REPORT: ReportModel = {
  question: 'Should Ridgeline Coffee open a second location on Mill Street?',
  filed: '22 Oct 2026',
  position: 'NEGATIVE',
  share: 0.82,
  caseAgainst: 'If the grease-trap upgrade lands on time, the Mill Street economics hold.',
  reasoning: ['The panel divided on timing, not on the location.'],
  whoHeldWhichView: [
    { position: 'NEGATIVE', names: ['Market analyst'] },
    { position: 'POSITIVE', names: ['Site analyst'] },
  ],
  sources: [{ document: 'Mill Street lease.pdf', reference: 'p.4' }],
  passes: [{ pass: 'P1', negative: 0.61, positive: 0.28, ambivalent: 0.11 }],
  panel: [
    {
      name: 'Tom Okafor',
      role: 'local regulator',
      position: 'NEGATIVE',
      confidence: 0.94,
      conviction: 0.95,
      receptivity: 0.1,
      turns: 4,
      weight: 0.89,
    },
  ],
  warnings: ['The demand study is a proxy.'],
}

describe('the exports speak the customer words', () => {
  it('writes the outcome and the panel positions in title case, never the enum', () => {
    expect(reportMarkdown(REPORT)).toContain('**Negative · 0.82 weighted share**')
    expect(reportMarkdown(REPORT)).toContain('| Tom Okafor (local regulator) | Negative |')
    expect(reportMarkdown(REPORT)).not.toContain('NEGATIVE')
    expect(reportHtml(REPORT)).toContain('Negative · 0.82 weighted share')
    expect(reportHtml(REPORT)).toContain('Tom Okafor (local regulator)')
    expect(reportHtml(REPORT)).not.toContain('>NEGATIVE<')
  })

  it('keeps the enum in json for machine consumers', () => {
    expect(JSON.parse(reportJson(REPORT)).outcome.stance).toBe('NEGATIVE')
    expect(JSON.parse(reportJson(REPORT)).outcome.share).toBe(0.82)
  })

  it('states a missing share, never invents one', () => {
    expect(reportMarkdown({ ...REPORT, share: null })).toContain('**Negative · — weighted share**')
    expect(JSON.parse(reportJson({ ...REPORT, share: null })).outcome.share).toBeNull()
  })
})
