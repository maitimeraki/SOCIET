import { describe, expect, it } from 'vitest'
import type { RunEvent } from './events'
import { RUN_SAMPLE } from './__fixtures__/run-sample'
import { applyEvent, fold, initialState } from './reducer'

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
    expect(fold(RUN_SAMPLE, NOW).roster.map((p) => p.identity.name)).toEqual(['D. Weber', 'M. Chen', 'P. Silva'])
  })
  it('fills the selection table from the selection event', () => {
    expect(fold(RUN_SAMPLE, NOW).selection[0]?.name).toBe('D. Weber')
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
    expect(state.verdict?.clusters?.POSITIVE?.count).toBe(3)
  })
  it('tolerates unknown event types as warnings', () => {
    const state = applyEvent(initialState, { type: 'future_thing' } as unknown as RunEvent, 1)
    expect(state.warnings).toContain('Unhandled event type: future_thing')
  })
  it('is deterministic — folding twice deep-equals (replay = live)', () => {
    expect(fold(RUN_SAMPLE, NOW)).toEqual(fold(RUN_SAMPLE, NOW))
  })
  it('records the failed state on error events', () => {
    expect(applyEvent(initialState, { type: 'error', error: 'boom' }, 1).status).toBe('failed')
  })
})
