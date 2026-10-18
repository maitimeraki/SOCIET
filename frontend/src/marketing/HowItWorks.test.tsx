import { describe, expect, it } from 'vitest'
// No jsdom in this repo — render to static markup in Node (see LandingPage.test.tsx).
import { renderToStaticMarkup } from 'react-dom/server'
import HowItWorks from './HowItWorks'
import { sections } from './copy'

const html = renderToStaticMarkup(<HowItWorks />)

describe('the traverse — four ruled steps', () => {
  it('renders every step title and its real-behaviour claim', () => {
    for (const step of sections.howItWorks.steps) {
      expect(html).toContain(step.title)
      expect(html).toContain(step.body)
    }
  })

  it('keys the steps to the legend and names the mechanism honestly', () => {
    expect(html).toContain(sections.howItWorks.traverseLegendTitle)
    // The third step is the argument itself — the pairing pass, named in the world's vocabulary.
    expect(html).toContain(sections.howItWorks.steps[2].title.toLowerCase())
    // The weighting is stated as it is computed — no invented figure.
    expect(html).toContain('CIOR')
  })
})

describe('the legend of what you get', () => {
  it('renders all five keyed lines, symbol + word', () => {
    expect(html).toContain(sections.howItWorks.gainsTitle)
    for (const gain of sections.howItWorks.gains) {
      expect(html).toContain(gain.label)
      expect(html).toContain(gain.body)
    }
  })

  it('draws a mark beside every line', () => {
    // Each gain line carries an authored mark; the section draws four traverse marks plus five gain
    // marks, so the svg count is a real floor, not a single decorative icon.
    expect(html.split('<svg').length - 1).toBeGreaterThanOrEqual(9)
  })
})
