import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import { BANNED_WORD, renderedText } from '../../test/copyLaw'
import Band from './Band'

describe('Band', () => {
  it('draws the tone as a class, so a surface reads the same wherever it is used', () => {
    for (const tone of ['page', 'band', 'sky', 'warm', 'plum', 'dark'] as const) {
      expect(renderToStaticMarkup(<Band tone={tone} />)).toContain(`band--${tone}`)
    }
  })

  it('tightens the band when it is dense', () => {
    expect(renderToStaticMarkup(<Band dense />)).toContain('band--dense')
    expect(renderToStaticMarkup(<Band />)).not.toContain('band--dense')
  })

  it('renders the element the caller asks for', () => {
    expect(renderToStaticMarkup(<Band />)).toContain('<section')
    expect(renderToStaticMarkup(<Band as="div" />)).toContain('<div')
    expect(renderToStaticMarkup(<Band as="footer" />)).toContain('<footer')
  })

  it('keeps the class string in the order the kit specifies', () => {
    const html = renderToStaticMarkup(<Band tone="band" dense id="x" />)
    expect(html).toContain('class="band band--band band--dense"')
    expect(html).toContain('id="x"')
  })

  it('renders no banned word — the copy law holds over the kit', () => {
    const html = renderToStaticMarkup(<Band>Documents</Band>)
    expect(renderedText(html)).not.toMatch(BANNED_WORD)
  })
})
