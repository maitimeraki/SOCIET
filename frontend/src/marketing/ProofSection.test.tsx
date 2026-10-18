import { describe, expect, it } from 'vitest'
// No jsdom in this repo — render to static markup in Node (see LandingPage.test.tsx).
import { renderToStaticMarkup } from 'react-dom/server'
import ProofSection from './ProofSection'

const html = renderToStaticMarkup(<ProofSection />)

describe('the proof section — the mechanism, never a mocked recording', () => {
  it('says plainly that no recording exists', () => {
    expect(html).toMatch(/no recording yet/i)
    expect(html).toContain('unedited capture of a real decision')
  })

  it('never emits a player, a fake frame or a screenshot', () => {
    // No recording and no capture exist, so nothing may imitate one.
    expect(html).not.toContain('<video')
    expect(html).not.toContain('<source')
    expect(html).not.toContain('<img')
    expect(html).not.toContain('.mp4')
    expect(html).not.toContain('aspect-video')
  })

  it('shows the three visible moments of a running decision', () => {
    expect(html).toContain('While a decision runs')
    expect(html).toContain('Your material, being read')
    expect(html).toContain('The panel, arguing in passes')
    expect(html).toContain('The answer, filed with its case')
  })
})
