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
    const html = render({ max_agents: 20, max_rounds: 4 })
    // `snapshot_top_k` also caps at 20, so exactly two fields carry max="20" — the capped
    // max_agents field and the untouched snapshot field.
    expect(html.match(/max="20"/g)).toHaveLength(2)
    expect(html).toContain('max="4"')
    expect(html).toContain('1–20')
    expect(html).toContain('1–4')
    // The other fields keep the server's absolute bound.
    expect(html).toContain('max="5"')
  })

  it('falls back to the absolute server bounds when no plan is known', () => {
    const html = render()
    expect(html).toContain('max="100"')
    expect(html).toContain('max="20"')
    expect(fieldMax('max_agents')).toBe(100)
    expect(fieldMax('max_rounds')).toBe(20)
  })

  it('never loosens a cap beyond the server bound', () => {
    expect(fieldMax('max_agents', { max_agents: 500, max_rounds: 50 })).toBe(100)
    expect(fieldMax('max_rounds', { max_agents: 500, max_rounds: 50 })).toBe(20)
  })
})
