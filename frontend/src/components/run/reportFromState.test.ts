import { describe, expect, it } from 'vitest'
import { applyStoredResult, fold, initialState } from '../../run/reducer'
import { RUN_SAMPLE } from '../../run/__fixtures__/run-sample'
import { reportFromState } from './reportFromState'

describe('reportFromState — the filed report, read from the folded run', () => {
  it('carries the report exactly as the backend wrote it', () => {
    const report = reportFromState(fold(RUN_SAMPLE, () => 0))
    expect(report?.reportStatus).toBe('produced')
    expect(report?.title).toBe('Should we expand into the European market in 2027?')
    expect(report?.markdown).toContain('Expand, cautiously, into one market first.')
    expect(report?.sources).toEqual({ '1': { document: 'EU market study 2026', section: 'Tariffs' } })
  })

  it('is null before a verdict is filed, so the tab says so rather than inventing one', () => {
    expect(reportFromState(initialState)).toBeNull()
  })

  it('reads a stored result when the event log predates the retry', () => {
    const filed = fold(
      [{ type: 'complete', converged: false, title: null, markdown: null, status: 'not_produced', final_stances: {}, warnings: [], rounds_executed: 0 }],
      () => 0,
    )
    const retried = reportFromState(
      applyStoredResult(filed, { status: 'produced', title: 'Expand?', markdown: '# Expand?', sources: {} }),
    )
    expect(retried?.reportStatus).toBe('produced')
    expect(retried?.markdown).toBe('# Expand?')
  })

  it('keeps no markdown and no sources for a report that was not produced', () => {
    const report = reportFromState(
      fold(
        [{ type: 'complete', converged: false, title: 'Ignored', markdown: 'Ignored', status: 'not_produced', sources: { '1': { document: 'D', section: 'S' } }, final_stances: {}, warnings: [], rounds_executed: 0 }],
        () => 0,
      ),
    )
    expect(report?.reportStatus).toBe('not_produced')
    expect(report?.markdown).toBeNull()
    expect(report?.title).toBeNull()
    expect(report?.sources).toEqual({})
  })
})
