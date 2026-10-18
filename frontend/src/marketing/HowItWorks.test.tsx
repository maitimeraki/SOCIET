import { describe, expect, it } from 'vitest'
// No jsdom in this repo — render to static markup in Node (see LandingPage.test.tsx).
import { renderToStaticMarkup } from 'react-dom/server'
import HowItWorks from './HowItWorks'

const html = renderToStaticMarkup(<HowItWorks />)

describe('the mechanism — four movements in order', () => {
  it('renders every step title and its real-behaviour claim', () => {
    for (const title of ['The material', 'The panel', 'The passes', 'The answer']) {
      expect(html).toContain(title)
    }
    expect(html).toContain('The order')
  })

  it('states the product truth: your documents, your panel, passes, a kept answer', () => {
    expect(html).toContain('You add your own documents')
    expect(html).toContain('The experts are drawn from that material')
    expect(html).toContain('argue in passes')
    expect(html).toContain('opposing case')
    expect(html).toContain('sources')
  })

  it('weights in plain words and invents no figure', () => {
    expect(html).toContain('weighted by confidence and conviction')
    expect(html).not.toMatch(/\d+%/)
  })
})

describe('what you get', () => {
  it('renders all five lines the decision leaves behind', () => {
    expect(html).toContain('What you get')
    for (const label of ['the answer', 'the opposing case', 'the positions', 'the sources', 'the record']) {
      expect(html).toContain(label)
    }
  })
})
