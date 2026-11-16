import { describe, expect, it } from 'vitest'
import { RUN_SAMPLE } from './__fixtures__/run-sample'
import { fold } from './reducer'
import { convergenceSeries, currentRound, railState, rosterProgress, streamItems, verdictView, STANCE_ORDER } from './selectors'

const NOW = () => 1_000
const full = fold(RUN_SAMPLE, NOW)

describe('selectors', () => {
  it('walks the roster phases in order as the fold progresses', () => {
    expect(rosterProgress(fold(RUN_SAMPLE.slice(0, 1), NOW)).phase).toBe('reading')
    expect(rosterProgress(fold(RUN_SAMPLE.slice(0, 3), NOW)).phase).toBe('reading')
    expect(rosterProgress(fold(RUN_SAMPLE.slice(0, 4), NOW)).phase).toBe('building')
    expect(rosterProgress(full).phase).toBe('seated')
  })
  it('reports k of n while profiles build', () => {
    const progress = rosterProgress(fold(RUN_SAMPLE.slice(0, 5), NOW))
    expect(progress.built).toBe(2)
    expect(progress.total).toBe(3)
  })
  it('shows the empty roster phase for a finished run with no agents', () => {
    const noAgents = fold(
      [
        { type: 'stage', stage: 'intake', index: 0, query: 'q' },
        { type: 'stage', stage: 'synthesis', index: 1, agents: 0 },
        { type: 'stage', stage: 'verdict', index: 2, converged: false, rounds_executed: 0 },
        { type: 'complete', converged: false, title: null, markdown: null, status: 'not_produced', final_stances: {}, warnings: [], rounds_executed: 0 },
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
    expect(Object.keys(series[1].weights ?? {})).toEqual(STANCE_ORDER)
  })
  it('streams round headers, turns, commits, activations and warnings in order', () => {
    const kinds = streamItems(full).map((item) => item.kind)
    expect(kinds.indexOf('round-header')).toBeLessThan(kinds.indexOf('turn'))
    expect(kinds.indexOf('turn')).toBeLessThan(kinds.indexOf('commit'))
    expect(kinds).toContain('activation')
  })
  it('carries the report markdown, its sources and its status into the verdict view', () => {
    const view = verdictView(full)
    expect(view?.markdown).toContain('## Recommendation')
    expect(view?.reportStatus).toBe('produced')
    expect(view?.sources).toEqual({ '1': { document: 'EU market study 2026', section: 'Tariffs' } })
  })
})

describe('the verdict view of a report that was not produced', () => {
  const notProduced = fold(
    [
      { type: 'stage', stage: 'intake', index: 0, query: 'q' },
      { type: 'round', round: 1, pairs: [], turns: [], consensus: null },
      { type: 'complete', converged: false, title: null, markdown: null, status: 'not_produced', final_stances: {}, warnings: [], rounds_executed: 1 },
    ],
    NOW,
  )

  it('keeps no markdown, title or sources, and says the report was not produced', () => {
    const view = verdictView(notProduced)
    expect(view?.reportStatus).toBe('not_produced')
    expect(view?.markdown).toBeNull()
    expect(view?.title).toBeNull()
    expect(view?.sources).toEqual({})
  })

  it('shows a pass with no weighted consensus as unshared, never as zero', () => {
    expect(convergenceSeries(notProduced)[0].weights).toBeNull()
  })
})
