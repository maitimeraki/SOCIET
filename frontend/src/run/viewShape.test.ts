import { describe, expect, it } from 'vitest'
import { InvalidAgentError, UnknownStanceError, asStance, parseAgentView, rosterFromEvents } from './events'
import type { AgentView, RunEvent, Stance } from './events'
import { RUN_SAMPLE } from './__fixtures__/run-sample'
import { INVALID_AGENT_WARNING, UNKNOWN_STANCE_WARNING, VERDICT_STANCE_WARNING, applyEvent, fold, initialState } from './reducer'

const VIEW_KEYS = ['bio', 'confidence', 'details', 'name', 'role', 'stance', 'strength', 'type']
const NOW = 1

const sampleView = (): AgentView => ({
  name: 'D. Weber',
  type: 'type unknown',
  role: 'Trade analyst',
  stance: 'POSITIVE',
  strength: 0.6,
  bio: 'Reads the tariff record.',
  details: 'The tariff alignment favours early expansion.',
  confidence: 0.7,
})

/** A pre-3.1 stored profile: the old identity/intensity/cior shape the current reader must skip. */
const legacyProfile = (): Record<string, unknown> => ({
  agent_id: 'a1',
  identity: { name: 'D. Weber', archetype: 'Trade analyst', communication_style: 'measured' },
  bio: 'Reads the tariff record.',
  detailed_perspective: 'I read the record.',
  stance: 'AMBIVALENT',
  intensity: 0.6,
  confidence: 0.7,
  conviction: 0.65,
  cior: 0.4,
  domain_tags: ['trade'],
  communication_radius: 1,
  summary_provenance: [],
  confidence_breakdown: { source_breadth: 1, node_density: 1, relationship_connectivity: 0.5 },
})

/** A non-empty prior state: the fixture through its first round, so the roster and rounds are populated. */
const PRIOR = fold(RUN_SAMPLE.slice(0, 12), () => NOW)

const roundEvent = (stance: unknown, consensus?: unknown): RunEvent =>
  ({
    type: 'round',
    round: 2,
    pairs: [],
    turns: [{ agent_id: 'a1', agent_name: 'D. Weber', content: 'x', stance, confidence: 0.5, references: [] }],
    consensus,
  }) as unknown as RunEvent

describe('stance parsing', () => {
  it('accepts ABSTAIN', () => expect(asStance('abstain')).toBe('ABSTAIN'))
  it('rejects an unknown stance instead of reading it as NEUTRAL', () => expect(() => asStance('sort of')).toThrow())
  it('rejects a null stance as an unknown stance, not a TypeError', () => expect(() => asStance(null)).toThrow(UnknownStanceError))
  it('rejects an undefined stance as an unknown stance, not a TypeError', () => expect(() => asStance(undefined)).toThrow(UnknownStanceError))
})

describe('agent view', () => {
  it('stores exactly the view keys for an agent event', () => {
    const state = applyEvent(initialState, { type: 'agent', index: 1, total: 1, profile: sampleView() }, NOW)
    expect(Object.keys(state.roster[0]).sort()).toEqual(VIEW_KEYS)
  })

  it('drops server keys the view does not name', () => {
    const profile = { ...sampleView(), evidence: [], cites: ['doc-1'], node_id: 'n1' } as unknown as AgentView
    const state = applyEvent(initialState, { type: 'agent', index: 1, total: 1, profile }, NOW)
    expect(Object.keys(state.roster[0]).sort()).toEqual(VIEW_KEYS)
  })

  it('turns a bad stance into a visible warning, not a crash', () => {
    const state = applyEvent(
      initialState,
      { type: 'agent', index: 1, total: 1, profile: { ...sampleView(), stance: 'maybe' as Stance } },
      NOW,
    )
    expect(state.warnings).toEqual([UNKNOWN_STANCE_WARNING])
  })

  it('keeps the non-empty prior roster when an agent event carries a bad stance', () => {
    const state = applyEvent(PRIOR, { type: 'agent', index: 4, total: 4, profile: { ...sampleView(), stance: 'maybe' as Stance } }, NOW)
    expect(state.roster).toEqual(PRIOR.roster)
  })

  it('advances the status out of queued even when the first agent event is skipped', () => {
    const state = applyEvent(initialState, { type: 'agent', index: 1, total: 1, profile: { ...sampleView(), stance: 'maybe' as Stance } }, NOW)
    expect(state.status).toBe('running')
  })

  it('skips a pre-3.1 stored profile with one warning and never throws', () => {
    const state = applyEvent(PRIOR, { type: 'agent', index: 4, total: 4, profile: legacyProfile() } as unknown as RunEvent, NOW)
    expect(state.roster).toEqual(PRIOR.roster)
    expect(state.warnings).toEqual([...PRIOR.warnings, INVALID_AGENT_WARNING])
  })

  it('rejects a pre-3.1 row in the projection', () => {
    expect(() => parseAgentView(legacyProfile())).toThrow(InvalidAgentError)
  })

  it('counts the stored profiles it cannot show, and keeps the rest', () => {
    const events = [
      { type: 'agent', index: 1, total: 2, profile: sampleView() },
      { type: 'agent', index: 2, total: 2, profile: legacyProfile() },
    ] as unknown as RunEvent[]
    expect(rosterFromEvents(events)).toEqual({ roster: [sampleView()], skipped: 1 })
  })
})

describe('round stances and weights', () => {
  it('keeps the prior rounds and warns when a turn carries a bad stance', () => {
    const state = applyEvent(PRIOR, roundEvent('maybe'), NOW)
    expect(state.rounds).toEqual(PRIOR.rounds)
    expect(state.warnings).toEqual([...PRIOR.warnings, UNKNOWN_STANCE_WARNING])
  })

  it('keeps the prior rounds when the consensus stance is null', () => {
    const state = applyEvent(PRIOR, roundEvent('POSITIVE', { stance: null, weight_share: 0.5, threshold: 0.8 }), NOW)
    expect(state.rounds).toEqual(PRIOR.rounds)
  })

  it('parses consensus weights through the closed set, ABSTAIN included', () => {
    const consensus = { stance: 'POSITIVE', weight_share: 0.6, threshold: 0.8, weights: { POSITIVE: 0.6, ABSTAIN: 0.4 } }
    const state = applyEvent(PRIOR, roundEvent('POSITIVE', consensus), NOW)
    expect(state.rounds[state.rounds.length - 1].consensus?.weights).toEqual({ POSITIVE: 0.6, ABSTAIN: 0.4 })
  })

  it('keeps the prior rounds when a weight key is outside the closed set', () => {
    const consensus = { stance: 'POSITIVE', weight_share: 0.6, threshold: 0.8, weights: { POSITIVE: 0.6, AMBIVALENT: 0.4 } }
    const state = applyEvent(PRIOR, roundEvent('POSITIVE', consensus), NOW)
    expect(state.rounds).toEqual(PRIOR.rounds)
    expect(state.warnings).toEqual([...PRIOR.warnings, UNKNOWN_STANCE_WARNING])
  })
})

describe('verdict stances', () => {
  const completeWith = (final_stances: Record<string, unknown>, cluster_details?: Record<string, unknown>): RunEvent =>
    ({ type: 'complete', converged: true, verdict: 'Done.', final_stances, warnings: [], rounds_executed: 2, cluster_details }) as unknown as RunEvent

  it('ends a live run as failed with the warning when a final stance is unknown, never NEUTRAL', () => {
    const state = applyEvent(PRIOR, completeWith({ 'D. Weber': 'maybe' }), NOW)
    expect(state.status).toBe('failed')
    expect(state.verdict).toBeNull()
    expect(state.warnings).toEqual([...PRIOR.warnings, VERDICT_STANCE_WARNING])
  })

  it('ends a reopened run the same way: folding the stored events reaches the same terminal state', () => {
    const reopened = fold([...RUN_SAMPLE.slice(0, 12), completeWith({}, { MAYBE: { stance: 'MAYBE' } })], () => NOW)
    expect(reopened.status).toBe('failed')
    expect(reopened.warnings).toContain(VERDICT_STANCE_WARNING)
  })

  it('still completes a verdict whose stances are all in the closed set, ABSTAIN included', () => {
    const state = applyEvent(PRIOR, completeWith({ 'D. Weber': 'abstain' }), NOW)
    expect(state.status).toBe('complete')
    expect(state.verdict?.finalStances).toEqual({ 'D. Weber': 'abstain' })
  })
})
