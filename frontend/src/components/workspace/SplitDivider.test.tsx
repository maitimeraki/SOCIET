import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import SplitDivider, {
  DEFAULT_RATIO,
  HANDLE_WIDTH,
  MAX_RATIO,
  MIN_RATIO,
  clampRatio,
  ratioFromKey,
  ratioFromPointer,
} from './SplitDivider'

describe('clampRatio', () => {
  it('keeps the ratio inside 30–70%', () => {
    expect(clampRatio(0.1)).toBe(0.3)
    expect(clampRatio(0.9)).toBe(0.7)
    expect(clampRatio(0.5)).toBe(0.5)
  })

  it('accepts its own bounds unchanged', () => {
    expect(clampRatio(MIN_RATIO)).toBe(0.3)
    expect(clampRatio(MAX_RATIO)).toBe(0.7)
  })
})

describe('ratioFromKey', () => {
  it('reads a stored ratio and falls back to the 40% default', () => {
    expect(ratioFromKey('0.5')).toBe(0.5)
    expect(ratioFromKey(null)).toBe(DEFAULT_RATIO)
    expect(ratioFromKey('nonsense')).toBe(DEFAULT_RATIO)
  })

  it('clamps a stored ratio that is out of range', () => {
    expect(ratioFromKey('0.9')).toBe(0.7)
    expect(ratioFromKey('0.1')).toBe(0.3)
  })
})

describe('the seam is one 1px column', () => {
  it('exports the handle width as a single pixel', () => {
    expect(HANDLE_WIDTH).toBe(1)
  })
})

describe('ratioFromPointer', () => {
  it('measures from the 1px handle’s centre, not its left edge', () => {
    // 1000px split; a cursor half a pixel past a track's left edge is that track's share exactly.
    expect(ratioFromPointer(300.5, 0, 1000)).toBe(0.3)
    expect(ratioFromPointer(500.5, 0, 1000)).toBe(0.5)
    expect(ratioFromPointer(700.5, 0, 1000)).toBe(0.7)
  })

  it('honours an explicit handle width and the split’s left offset', () => {
    expect(ratioFromPointer(404, 100, 1000, 8)).toBe(0.3)
    expect(ratioFromPointer(604, 100, 1000, 8)).toBe(0.5)
  })

  it('clamps past either edge', () => {
    expect(ratioFromPointer(-500, 0, 1000)).toBe(0.3)
    expect(ratioFromPointer(5000, 0, 1000)).toBe(0.7)
  })
})

describe('SplitDivider', () => {
  it('renders a keyboard separator with its value and the 30–70 bounds', () => {
    const html = renderToStaticMarkup(<SplitDivider ratio={0.4} onChange={() => {}} />)
    expect(html).toContain('role="separator"')
    expect(html).toContain('aria-label="Resize the map and the work"')
    expect(html).toContain('aria-orientation="vertical"')
    expect(html).toContain('aria-valuenow="40"')
    expect(html).toContain('aria-valuemin="30"')
    expect(html).toContain('aria-valuemax="70"')
    expect(html).toContain('tabindex="0"')
  })

  it('is hidden below lg and laid out as a 1px drag handle from lg up', () => {
    const html = renderToStaticMarkup(<SplitDivider ratio={0.5} onChange={() => {}} />)
    expect(html).toContain('hidden')
    expect(html).toContain('lg:flex')
    expect(html).toContain('cursor-col-resize')
    expect(html).toContain('bg-hairline')
    // The grip mark is the 1px rule itself, never a typographic glyph.
    expect(html).toContain('h-11 w-px bg-rule')
    expect(html).not.toContain('⋮')
  })
})
