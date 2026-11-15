import { describe, expect, it } from 'vitest'
import { asStance, type AgentView, type Stance } from './events'
import { applyEvent, initialState } from './reducer'

const VIEW_KEYS = ['bio', 'confidence', 'details', 'name', 'role', 'stance', 'strength', 'type']

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

describe('agent view', () => {
  it('accepts ABSTAIN', () => expect(asStance('abstain')).toBe('ABSTAIN'))
  it('rejects an unknown stance instead of reading it as NEUTRAL', () => expect(() => asStance('sort of')).toThrow())
  it('stores exactly the view keys for an agent event', () => {
    const state = applyEvent(initialState, { type: 'agent', index: 1, total: 1, profile: sampleView() }, 1)
    expect(Object.keys(state.roster[0]).sort()).toEqual(VIEW_KEYS)
  })
  it('turns a bad stance into a visible warning, not a crash', () => {
    const state = applyEvent(
      initialState,
      { type: 'agent', index: 1, total: 1, profile: { ...sampleView(), stance: 'maybe' as Stance } },
      1,
    )
    expect(state.warnings.join(' ')).toMatch(/stance/i)
  })
  it('keeps the previous roster when an agent event carries a bad stance', () => {
    const state = applyEvent(
      initialState,
      { type: 'agent', index: 1, total: 1, profile: { ...sampleView(), stance: 'maybe' as Stance } },
      1,
    )
    expect(state.roster).toEqual([])
  })
  it('turns a bad round stance into a warning and keeps the previous rounds', () => {
    const state = applyEvent(
      initialState,
      {
        type: 'round',
        round: 1,
        pairs: [],
        turns: [{ agent_id: 'a1', agent_name: 'D. Weber', content: 'x', stance: 'maybe', confidence: 0.5, references: [] }],
      },
      1,
    )
    expect(state.rounds).toEqual([])
    expect(state.warnings.join(' ')).toMatch(/stance/i)
  })
})
