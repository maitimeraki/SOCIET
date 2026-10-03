import { describe, expect, it } from 'vitest'
import { RUN_SAMPLE } from './__fixtures__/run-sample'
import { fold } from './reducer'
import { convergenceSeries, currentRound, railState, rosterProgress, streamItems, verdictView, STANCE_ORDER } from './selectors'

const NOW = () => 1_000
const full = fold(RUN_SAMPLE, NOW)

describe('selectors', () => {
  it('walks the roster phases in order as the fold progresses', () => {
    expect(rosterProgress(fold(RUN_SAMPLE.slice(0, 1), NOW)).phase).toBe('reading')
    expect(rosterProgress(fold(RUN_SAMPLE.slice(0, 4), NOW)).phase).toBe('selecting')
    expect(rosterProgress(fold(RUN_SAMPLE.slice(0, 5), NOW)).phase).toBe('building')
    expect(rosterProgress(full).phase).toBe('seated')
  })
  it('reports k of n while profiles build', () => {
    const progress = rosterProgress(fold(RUN_SAMPLE.slice(0, 6), NOW))
    expect(progress.built).toBe(2)
    expect(progress.total).toBe(3)
  })
  it('shows the empty roster phase for a finished run with no agents', () => {
    const noAgents = fold(
      [
        { type: 'stage', stage: 'intake', index: 0, query: 'q' },
        { type: 'stage', stage: 'synthesis', index: 1, agents: 0 },
        { type: 'stage', stage: 'verdict', index: 2, converged: false, rounds_executed: 0 },
        { type: 'complete', converged: false, verdict: 'No agents', final_stances: {}, warnings: [], rounds_executed: 0 },
      ],
      NOW,
    )
    expect(rosterProgress(noAgents).phase).toBe('empty')
  })
  it('rails the completed run as all done', () => {
    expect(railState(full).map((entry) => entry.state)).toEqual(['done', 'done', 'done', 'done', 'done', 'done'])
  })
  it('rails a mid-roster run with roster running', () => {
    const rail = railState(fold(RUN_SAMPLE.slice(0, 5), NOW))
    expect(rail.find((entry) => entry.key === 'roster')?.state).toBe('running')
    expect(rail.find((entry) => entry.key === 'debate')?.state).toBe('pending')
  })
  it('reads the current round', () => {
    expect(currentRound(full)).toBe(2)
  })
  it('serialises one tape tick per round with canonical weights', () => {
    const series = convergenceSeries(full)
    expect(series).toHaveLength(2)
    expect(Object.keys(series[1].weights)).toEqual(STANCE_ORDER)
  })
  it('streams round headers, turns, commits, activations and warnings in order', () => {
    const kinds = streamItems(full).map((item) => item.kind)
    expect(kinds.indexOf('round-header')).toBeLessThan(kinds.indexOf('turn'))
    expect(kinds.indexOf('turn')).toBeLessThan(kinds.indexOf('commit'))
    expect(kinds).toContain('activation')
  })
  it('projects the verdict view with the dominant weighted stance', () => {
    const view = verdictView(full)
    expect(view?.stance).toBe('POSITIVE')
    expect(view?.confidence).toBe(0.83)
  })
})
