import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import Figure from './Figure'

describe('Figure', () => {
  it('is mono and tabular — a figure never competes with prose', () => {
    const html = renderToStaticMarkup(<Figure value="0.82" />)
    expect(html).toContain('font-measurement')
    expect(html).toContain('tnum')
  })

  it('takes the card scale or the panel scale', () => {
    expect(renderToStaticMarkup(<Figure value="0.82" />)).toContain('text-mono-lg')
    expect(renderToStaticMarkup(<Figure value="0.82" size="numeral" />)).toContain('text-numeral')
  })

  it('gives the two sizes different classes', () => {
    const small = renderToStaticMarkup(<Figure value="0.82" />)
    const large = renderToStaticMarkup(<Figure value="0.82" size="numeral" />)
    expect(small).not.toBe(large)
  })

  it('carries the label and the hint when they are given', () => {
    const html = renderToStaticMarkup(<Figure value="0.82" label="the share" hint="of the panel" />)
    expect(html).toContain('the share')
    expect(html).toContain('of the panel')
  })
})
