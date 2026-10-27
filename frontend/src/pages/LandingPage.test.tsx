import { describe, expect, it } from 'vitest'
import type { RunSummary } from '../api/types'
import { landingTarget } from './LandingPage'

const run = (patch: Partial<RunSummary> = {}): RunSummary => ({
  run_id: 'r1', created_at: '2026-10-12T10:00:00Z', query: 'q', corpus_label: null,
  dataset_id: 'd1', status: 'complete', rounds_executed: 3, converged: true, verdict_stance: 'NEGATIVE', ...patch,
})

describe('landingTarget', () => {
  it('sends an empty account to Documents', () => {
    expect(landingTarget(0, [])).toBe('/documents')
  })
  it('sends material with no answer to Runs', () => {
    expect(landingTarget(3, [run({ verdict_stance: null, status: 'running' })])).toBe('/runs')
  })
  it('sends a filed answer to Verdict', () => {
    expect(landingTarget(3, [run()])).toBe('/results')
  })
})
