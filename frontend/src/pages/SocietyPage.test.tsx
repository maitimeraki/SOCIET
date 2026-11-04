import { afterEach, describe, expect, it } from 'vitest'
import { clampConfig, debateRequest, initialConfig } from './SocietyPage'
import { DEBATE_CONFIG_DEFAULTS } from '../api/types'
import type { User } from '../api/types'
import { useAuthStore } from '../auth/authStore'

afterEach(() => useAuthStore.getState().clear())

// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx), and zustand serves its
// *initial* state to `renderToStaticMarkup` — so the corpus name cannot be injected for a server
// render. The request the step would send is a pure function of its inputs instead: both the gate
// (nothing before extraction) and the label are asserted here, against the code that sends them.

const CONFIG = DEBATE_CONFIG_DEFAULTS

describe('the question cannot become a request before the map exists (§9, D3)', () => {
  it('refuses a request with no graph id — extraction has not finished', () => {
    expect(debateRequest(null, 'EU expansion', 'Should we expand?', CONFIG)).toBeNull()
  })

  it('refuses a request with no question, however the map stands', () => {
    expect(debateRequest('ds-1', 'EU expansion', '   ', CONFIG)).toBeNull()
  })
})

describe('the form starts inside the plan (§7.10)', () => {
  it('a free plan starts at 10 experts and 3 passes, not the absolute 50/5', () => {
    expect(initialConfig({ max_agents: 10, max_rounds: 3 })).toMatchObject({
      max_agents: 10,
      max_rounds: 3,
    })
  })

  it('a signup/login response carries its caps through the auth store into the form', () => {
    const signup: User = {
      id: 'u1',
      email: 'a@b.c',
      created_at: '2026-01-01T00:00:00Z',
      role: 'user',
      plan: 'free',
      entitlements: {
        max_agents: 10,
        max_rounds: 3,
        units_remaining: 1000,
        period_end: '2026-12-01T00:00:00Z',
      },
    }

    useAuthStore.getState().setUser(signup)
    const config = initialConfig(useAuthStore.getState().user?.entitlements)

    expect(config.max_agents).toBe(10)
    expect(config.max_rounds).toBe(3)
    expect(config.max_agents).not.toBe(DEBATE_CONFIG_DEFAULTS.max_agents)
    expect(config.max_rounds).not.toBe(DEBATE_CONFIG_DEFAULTS.max_rounds)
  })

  it('keeps the absolute defaults when no plan cap is known', () => {
    expect(initialConfig()).toMatchObject({
      max_agents: DEBATE_CONFIG_DEFAULTS.max_agents,
      max_rounds: DEBATE_CONFIG_DEFAULTS.max_rounds,
    })
  })

  it('clamps an already-edited config when the plan caps change', () => {
    const edited = { ...DEBATE_CONFIG_DEFAULTS, max_agents: 40, max_rounds: 12 }
    expect(clampConfig(edited, { max_agents: 10, max_rounds: 3 })).toMatchObject({
      max_agents: 10,
      max_rounds: 3,
    })
  })
})

describe('submitting sends the client corpus name as the label, beside the graph id', () => {
  it('carries corpus_label and graph_id', () => {
    expect(debateRequest('ds-1', 'EU expansion', 'Should we expand?', CONFIG)).toMatchObject({
      graph_id: 'ds-1',
      corpus_label: 'EU expansion',
      query: 'Should we expand?',
    })
  })
})
