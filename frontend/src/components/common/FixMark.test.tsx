import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import FixMark from './FixMark'

describe('FixMark', () => {
  it('draws the ink ring, the warn centre and the vermilion plotted point', () => {
    const html = renderToStaticMarkup(<FixMark confidence={0.82} />)
    expect(html).toContain('stroke="currentColor"') // the ink ring follows its ground
    expect(html).toContain('--color-warn') // the centre
    expect(html).toContain('--color-danger') // the plotted point
  })

  it('is always accompanied by the confidence figure, in the measurement face', () => {
    const html = renderToStaticMarkup(<FixMark confidence={0.82} />)
    expect(html).toContain('font-mono')
    expect(html).toContain('0.82')
  })

  it('shows a placeholder rather than a fabricated zero when there is no confidence', () => {
    const html = renderToStaticMarkup(<FixMark confidence={null} />)
    expect(html).toContain('—')
    expect(html).not.toContain('0.00')
  })

  it('takes the fix motion — the plotted point blooms once and settles (§5)', () => {
    expect(renderToStaticMarkup(<FixMark confidence={0.5} />)).toContain('fix')
  })
})
