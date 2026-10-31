import { describe, expect, it } from 'vitest'
// Node-only, like the rest of the suite: the derivation is pure, so it is read directly.
import { fold } from '../../run/reducer'
import { RUN_SAMPLE } from '../../run/__fixtures__/run-sample'
import { reportFromState } from './reportFromState'

// The fold clock is deliberately NOT the stored day: the report reads the run doc's stored date, not
// the moment the buffer was refolded (R59).
const FOLD_CLOCK = Date.UTC(2026, 10, 5, 14, 0)
const STORED_AT = '2026-10-22T09:30:00Z'
const STATE = fold(RUN_SAMPLE, () => FOLD_CLOCK)
const REPORT = reportFromState(STATE, STORED_AT)!

describe('the filed report is derived from folded run state (R57)', () => {
  it('carries the question, the stored filing day, the position and the share', () => {
    expect(REPORT.question).toBe('Should we expand into the European market in 2027?')
    expect(REPORT.filed).toBe('22 Oct 2026')
    expect(REPORT.position).toBe('POSITIVE')
    expect(REPORT.share).toBe(0.83)
  })

  it('reads the stored day even when a reopened run is refolded later', () => {
    const reopened = fold(RUN_SAMPLE, () => Date.UTC(2026, 11, 1, 8, 0))
    expect(reportFromState(reopened, STORED_AT)?.filed).toBe('22 Oct 2026')
  })

  it('takes the case against from the first dissenting view', () => {
    expect(REPORT.caseAgainst).toBe('Entry cost outweighs the single market.')
  })

  it('states the honest fallback when no dissent was recorded', () => {
    const noDissent = reportFromState({ ...STATE, verdict: { ...STATE.verdict!, dissentingViews: [] } }, STORED_AT)
    expect(noDissent?.caseAgainst).toBe('No dissent was recorded.')
  })

  it('reads the reasoning as prose — the summary, then the narrative bodies without their marks', () => {
    expect(REPORT.reasoning).toEqual([
      'The debate concluded with 67% of turns expressing POSITIVE stance. Confidence score: 0.83.',
      'Expand, cautiously.',
      'Steel tariffs bite the entry cost.',
    ])
  })

  it('does not print a fallback narrative twice — a fallback narrative is the summary', () => {
    const verdict = STATE.verdict!
    const fallback = reportFromState(
      { ...STATE, verdict: { ...verdict, narrative: verdict.summary, narrativeStatus: 'fallback' } },
      STORED_AT,
    )
    expect(fallback?.reasoning).toEqual([verdict.summary])
  })

  it('groups who held which view in STANCE_ORDER and drops empty groups', () => {
    expect(REPORT.whoHeldWhichView).toEqual([
      { position: 'POSITIVE', names: ['D. Weber', 'P. Silva'] },
      { position: 'NEGATIVE', names: ['M. Chen'] },
    ])
  })

  it('names the sources from the roster provenance, once each, with their breadcrumb', () => {
    expect(REPORT.sources).toEqual([{ document: 'eu-market-2027.pdf', reference: 'Section 3' }])
  })

  it('keeps an empty reference when the roster recorded no breadcrumb', () => {
    const bare = {
      ...STATE,
      roster: STATE.roster.map((profile) => ({
        ...profile,
        summary_provenance: profile.summary_provenance.map((link) => ({ ...link, breadcrumb: undefined })),
      })),
    }
    expect(reportFromState(bare, STORED_AT)?.sources).toEqual([{ document: 'eu-market-2027.pdf', reference: '' }])
  })

  it('reads the passes through the convergence series the tape reads', () => {
    expect(REPORT.passes).toEqual([
      { pass: 'P1', negative: 0.2, positive: 0.55, ambivalent: 0.1 },
      { pass: 'P2', negative: 0.15, positive: 0.72, ambivalent: 0.05 },
    ])
  })

  it('reads the panel from the roster and the turns, with the CIOR weight', () => {
    expect(REPORT.panel.map((row) => [row.name, row.role, row.position, row.turns])).toEqual([
      ['D. Weber', 'Trade analyst', 'POSITIVE', 2],
      // The final stance wins over the opening one: P. Silva opened NEUTRAL and ended POSITIVE.
      ['M. Chen', 'Entry-cost strategist', 'NEGATIVE', 2],
      ['P. Silva', 'Policy analyst', 'POSITIVE', 2],
    ])
    const [weber, chen, silva] = REPORT.panel
    expect(weber.confidence).toBe(0.7)
    expect(weber.conviction).toBe(0.65)
    expect(weber.receptivity).toBe(0.4)
    expect(weber.weight).toBeCloseTo((0.7 * 0.65 * 1.4) / 2)
    expect(chen.receptivity).toBe(-0.4)
    expect(chen.weight).toBeCloseTo((0.7 * 0.65 * 0.6) / 2)
    expect(silva.weight).toBeCloseTo((0.7 * 0.65) / 2)
  })

  it('carries the run warnings', () => {
    const warned = reportFromState({ ...STATE, warnings: ['The demand study is a proxy.'] }, STORED_AT)
    expect(warned?.warnings).toEqual(['The demand study is a proxy.'])
  })

  it('is null before a verdict is filed — the tab states that, never a fabricated report', () => {
    expect(reportFromState({ ...STATE, verdict: null }, STORED_AT)).toBeNull()
  })

  it('states a dash when the store has no stored filing date — never the fold clock', () => {
    expect(reportFromState(STATE, null)?.filed).toBe('—')
  })
})
