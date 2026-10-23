import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import Meter from './Meter'

describe('Meter', () => {
  it('draws the share, and sets the figure beside it in the measurement face', () => {
    const html = renderToStaticMarkup(<Meter value={0.82} label="share" display="0.82" />)
    expect(html).toContain('0.82')
    expect(html).toContain('font-measurement')
    expect(html).toContain('tnum')
  })

  it('fills the track by the share it is given', () => {
    const html = renderToStaticMarkup(<Meter value={0.25} label="share" display="0.25" />)
    expect(html).toContain('width:25%')
  })

  it('never fills beyond the track', () => {
    expect(renderToStaticMarkup(<Meter value={2} label="share" display="2" />)).toContain('width:100%')
    expect(renderToStaticMarkup(<Meter value={-1} label="share" display="0" />)).toContain('width:0%')
  })

  it('takes the accent fill or the quiet ink fill', () => {
    expect(renderToStaticMarkup(<Meter value={1} label="s" display="1" />)).toContain('bg-accent')
    expect(renderToStaticMarkup(<Meter value={1} label="s" display="1" tone="ink" />)).toContain('bg-ink')
  })

  it('takes the short track or the full-width one', () => {
    expect(renderToStaticMarkup(<Meter value={1} label="s" display="1" />)).toContain('w-14')
    expect(renderToStaticMarkup(<Meter value={1} label="s" display="1" width="full" />)).toContain('flex-1')
  })

  it('rounds its track on the radius token, never a literal', () => {
    expect(renderToStaticMarkup(<Meter value={1} label="s" display="1" />)).toContain('rounded-xs')
  })
})
