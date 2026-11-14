import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { DEBATE_CONFIG_DEFAULTS } from '../../api/types'
import ConfigPanel, { fieldMax } from './ConfigPanel'

const render = (limits?: { max_agents: number; max_rounds: number }) => {
  const value = limits
    ? { ...DEBATE_CONFIG_DEFAULTS, max_agents: limits.max_agents, max_rounds: limits.max_rounds }
    : DEBATE_CONFIG_DEFAULTS
  return renderToStaticMarkup(<ConfigPanel value={value} onChange={() => {}} limits={limits} />)
}

describe('ConfigPanel — the plan caps', () => {
  it('caps the two plan-bound fields at the plan limit, with the cap in the hint', () => {
    const html = render({ max_agents: 8, max_rounds: 4 })
    // The seat cap (8) and the pass cap (4) are the plan's; snapshot_top_k keeps its server bound of 20.
    expect(html).toContain('max="8"')
    expect(html).toContain('max="4"')
    expect(html).toContain('1–8')
    expect(html).toContain('1–4')
    // The other fields keep the server's absolute bound.
    expect(html).toContain('max="5"')
  })

  it('falls back to the absolute server bounds when no plan is known', () => {
    const html = render()
    expect(html).toContain('max="12"')
    expect(html).toContain('max="20"')
    expect(fieldMax('max_agents')).toBe(12)
    expect(fieldMax('max_rounds')).toBe(20)
  })

  it('never loosens a cap beyond the server bound', () => {
    expect(fieldMax('max_agents', { max_agents: 500, max_rounds: 50 })).toBe(12)
    expect(fieldMax('max_rounds', { max_agents: 500, max_rounds: 50 })).toBe(20)
  })
})
