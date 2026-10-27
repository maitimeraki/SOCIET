import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import SplitDivider, { MAX_RATIO, MIN_RATIO, clampRatio, ratioFromKey } from './SplitDivider'

describe('clampRatio', () => {
  it('keeps the ratio inside 25–75%', () => {
    expect(clampRatio(0.1)).toBe(0.25)
    expect(clampRatio(0.9)).toBe(0.75)
    expect(clampRatio(0.5)).toBe(0.5)
  })

  it('accepts its own bounds unchanged', () => {
    expect(clampRatio(MIN_RATIO)).toBe(0.25)
    expect(clampRatio(MAX_RATIO)).toBe(0.75)
  })
})

describe('ratioFromKey', () => {
  it('reads a stored ratio and falls back to 50%', () => {
    expect(ratioFromKey('0.4')).toBe(0.4)
    expect(ratioFromKey(null)).toBe(0.5)
    expect(ratioFromKey('nonsense')).toBe(0.5)
  })

  it('clamps a stored ratio that is out of range', () => {
    expect(ratioFromKey('0.9')).toBe(0.75)
  })
})

describe('SplitDivider', () => {
  it('renders a keyboard separator with its value', () => {
    const html = renderToStaticMarkup(<SplitDivider ratio={0.4} onChange={() => {}} />)
    expect(html).toContain('role="separator"')
    expect(html).toContain('aria-orientation="vertical"')
    expect(html).toContain('aria-valuenow="40"')
    expect(html).toContain('aria-valuemin="25"')
    expect(html).toContain('aria-valuemax="75"')
    expect(html).toContain('tabindex="0"')
  })

  it('is hidden below lg and laid out as a drag handle from lg up', () => {
    const html = renderToStaticMarkup(<SplitDivider ratio={0.5} onChange={() => {}} />)
    expect(html).toContain('hidden')
    expect(html).toContain('lg:flex')
    expect(html).toContain('cursor-col-resize')
  })
})
