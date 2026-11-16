import { describe, expect, it } from 'vitest'
import type { RunEvent } from './events'
import { RUN_SAMPLE } from './__fixtures__/run-sample'
import { applyEvent, applyStoredResult, fold, initialState } from './reducer'

const NOW = () => 1_000

describe('reducer', () => {
  it('folds the fixture into a complete run state', () => {
    expect(fold(RUN_SAMPLE, NOW).status).toBe('complete')
  })
  it('captures the intent, query and dataset', () => {
    const state = fold(RUN_SAMPLE, NOW)
    expect(state.query).toBe('Should we expand into the European market in 2027?')
    expect(state.datasetId).toBe('ds-fixture')
    expect(state.intent?.core_question).toBe('market-entry risk vs opportunity in EU steel')
  })
  it('builds the roster in agent-event order', () => {
    expect(fold(RUN_SAMPLE, NOW).roster.map((p) => p.name)).toEqual(['D. Weber', 'M. Chen', 'P. Silva'])
  })
  it('collects rounds with consensus weights', () => {
    expect(fold(RUN_SAMPLE, NOW).rounds[1]?.consensus?.weights?.POSITIVE).toBeCloseTo(0.72)
  })
  it('records commits and activations', () => {
    const state = fold(RUN_SAMPLE, NOW)
    expect(state.commits.map((commit) => commit.round)).toEqual([1, 2])
    expect(state.activations[0]?.agents).toEqual(['L. Novak'])
  })
  it('parses pair_turn ids into the live pair map', () => {
    const state = applyEvent(initialState, { type: 'pair_turn', pair_id: 'ds1:A:B', response: null, error: null }, 1)
    expect(state.livePairs['ds1:A:B']).toEqual({ a: 'A', b: 'B', startedAt: 1 })
  })
  it('clears live pairs when the round arrives', () => {
    const withPair = applyEvent(initialState, { type: 'pair_turn', pair_id: 'ds1:A:B', response: null, error: null }, 1)
    const state = applyEvent(withPair, { type: 'round', round: 1, pairs: [], turns: [] }, 2)
    expect(state.livePairs).toEqual({})
  })
  it('builds the verdict from the complete event', () => {
    const state = fold(RUN_SAMPLE, NOW)
    expect(state.verdict?.converged).toBe(true)
    expect(state.verdict?.reportStatus).toBe('produced')
  })
  it('keeps only the public document and section of each source, whatever else the event carries', () => {
    const leaky = { '1': { document: 'D', section: 'S', chunk_id: 'chunk-1' } }
    const state = applyEvent(
      initialState,
      { type: 'complete', converged: true, title: 'T', markdown: '# T', status: 'produced', sources: leaky, final_stances: {}, warnings: [], rounds_executed: 1 },
      1,
    )
    expect(state.verdict?.sources).toEqual({ '1': { document: 'D', section: 'S' } })
  })
  it('carries the report title, markdown and sources off the complete event', () => {
    const state = applyEvent(
      initialState,
      {
        type: 'complete',
        converged: true,
        title: 'Expand?',
        markdown: '# Expand?\n## Recommendation\nExpand.',
        status: 'produced',
        sources: { '1': { document: 'Study', section: 'Costs' } },
        final_stances: {},
        warnings: [],
        rounds_executed: 1,
      },
      1,
    )
    expect(state.verdict?.reportStatus).toBe('produced')
    expect(state.verdict?.title).toBe('Expand?')
    expect(state.verdict?.markdown).toContain('## Recommendation')
    expect(state.verdict?.sources).toEqual({ '1': { document: 'Study', section: 'Costs' } })
  })
  it('keeps no title, markdown or sources for a report that was not produced', () => {
    const state = applyEvent(
      initialState,
      { type: 'complete', converged: false, title: null, markdown: null, status: 'not_produced', sources: {}, final_stances: {}, warnings: [], rounds_executed: 0 },
      1,
    )
    expect(state.verdict?.reportStatus).toBe('not_produced')
    expect(state.verdict?.title).toBeNull()
    expect(state.verdict?.markdown).toBeNull()
    expect(state.verdict?.sources).toEqual({})
  })
  it('reads a stored result over the complete event it was filed with, once a retry has written it', () => {
    const filed = applyEvent(
      initialState,
      { type: 'complete', converged: false, title: null, markdown: null, status: 'not_produced', final_stances: {}, warnings: [], rounds_executed: 0 },
      1,
    )
    const retried = applyStoredResult(filed, {
      status: 'produced',
      converged: false,
      title: 'Expand?',
      markdown: '# Expand?',
      sources: {},
      final_stances: {},
    })
    expect(retried.verdict?.reportStatus).toBe('produced')
    expect(retried.verdict?.markdown).toBe('# Expand?')
  })
  it('leaves the verdict alone when the stored result carries no report status', () => {
    const filed = applyEvent(
      initialState,
      { type: 'complete', converged: true, title: null, markdown: null, status: 'not_produced', final_stances: {}, warnings: [], rounds_executed: 0 },
      1,
    )
    expect(applyStoredResult(filed, { intent: null })).toBe(filed)
    expect(applyStoredResult(filed, null)).toBe(filed)
  })
  it('tolerates unknown event types as warnings', () => {
    const state = applyEvent(initialState, { type: 'future_thing' } as unknown as RunEvent, 1)
    expect(state.warnings).toContain('Unhandled event type: future_thing')
  })
  it('names a failed commit by its pass, never a banned word — the composed warning reaches the page (§13, F46)', () => {
    const state = applyEvent(
      initialState,
      { type: 'commit', round: 2, opinions: 0, edges: 0, failed: true, error: 'connection reset' },
      1,
    )
    expect(state.warnings[0]).toBe('Pass 2: commit failed: connection reset')
    expect(state.warnings.join(' ')).not.toMatch(/\bround\b/i)
  })
  it('is deterministic — folding twice deep-equals (replay = live)', () => {
    expect(fold(RUN_SAMPLE, NOW)).toEqual(fold(RUN_SAMPLE, NOW))
  })
  it('records the failed state on error events', () => {
    expect(applyEvent(initialState, { type: 'error', error: 'boom' }, 1).status).toBe('failed')
  })
})
