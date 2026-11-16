import { describe, expect, it } from 'vitest'
import { RUN_SAMPLE } from './__fixtures__/run-sample'
import type { ClusterSummary, Stance } from './events'
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
  it('projects the verdict view with the dominant weighted stance', () => {
    const view = verdictView(full)
    expect(view?.stance).toBe('POSITIVE')
    expect(view?.confidence).toBe(0.83)
  })
  it('carries the report markdown, its sources and its status into the verdict view', () => {
    const view = verdictView(full)
    expect(view?.markdown).toContain('## Recommendation')
    expect(view?.reportStatus).toBe('produced')
    expect(view?.sources).toEqual({ '1': { document: 'EU market study 2026', section: 'Tariffs' } })
  })
})

describe('the verdict stance and the tape without a weighted position', () => {
  const cluster = (stance: Stance, total_weight: number): ClusterSummary => ({
    stance,
    count: 1,
    total_weight,
    avg_confidence: 0.5,
    avg_conviction: 0.5,
    agents: ['Alpha'],
  })
  const round = (number: number, consensus: null | undefined) => ({
    type: 'round' as const,
    round: number,
    pairs: [],
    turns: [],
    consensus,
  })
  const completed = (cluster_details: Record<string, ClusterSummary> | undefined, final_stances: Record<string, string> = {}) =>
    fold(
      [
        { type: 'stage', stage: 'intake', index: 0, query: 'q' },
        round(1, null),
        {
          type: 'complete' as const,
          converged: false,
          title: null,
          markdown: null,
          status: 'not_produced' as const,
          final_stances,
          warnings: [],
          rounds_executed: 1,
          confidence_score: 0,
          cluster_details: cluster_details as Record<Stance, ClusterSummary> | undefined,
        },
      ],
      NOW,
    )

  it('takes no stance, no share, and no tape shares when no cluster carries weight', () => {
    const state = completed({ ABSTAIN: cluster('ABSTAIN', 0) }, { Alpha: 'ABSTAIN' })
    const view = verdictView(state)
    expect(view?.stance).toBeNull()
    expect(view?.confidence).toBeNull()
    expect(view?.reportStatus).toBe('not_produced')
    expect(view?.markdown).toBeNull()
    expect(convergenceSeries(state)[0].weights).toBeNull()
  })

  it('breaks a weight tie in POSITIVE, NEGATIVE, NEUTRAL order', () => {
    const negativeOverNeutral = verdictView(completed({ NEUTRAL: cluster('NEUTRAL', 0.5), NEGATIVE: cluster('NEGATIVE', 0.5) }))
    const positiveOverNeutral = verdictView(completed({ NEUTRAL: cluster('NEUTRAL', 0.5), POSITIVE: cluster('POSITIVE', 0.5) }))
    expect(negativeOverNeutral?.stance).toBe('NEGATIVE')
    expect(positiveOverNeutral?.stance).toBe('POSITIVE')
  })

  it('takes no stance from agent counts when the verdict carries no clusters', () => {
    const view = verdictView(completed(undefined, { Alpha: 'POSITIVE', Beta: 'POSITIVE', Gamma: 'NEGATIVE' }))
    expect(view?.stance).toBeNull()
  })
})
