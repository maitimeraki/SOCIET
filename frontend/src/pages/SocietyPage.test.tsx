import { describe, expect, it } from 'vitest'
import { debateRequest } from './SocietyPage'
import { DEBATE_CONFIG_DEFAULTS } from '../api/types'

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

describe('submitting sends the client corpus name as the label, beside the graph id', () => {
  it('carries corpus_label and graph_id', () => {
    expect(debateRequest('ds-1', 'EU expansion', 'Should we expand?', CONFIG)).toMatchObject({
      graph_id: 'ds-1',
      corpus_label: 'EU expansion',
      query: 'Should we expand?',
    })
  })
})
