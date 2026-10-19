import { describe, expect, it } from 'vitest'
// No jsdom in this repo — render to static markup in Node (see LandingPage.test.tsx).
import { renderToStaticMarkup } from 'react-dom/server'
import ProofSection from './ProofSection'
import { captures, sections } from './copy'

const html = renderToStaticMarkup(<ProofSection />)

describe('the proof section — the mechanism, never a mocked recording', () => {
  it('says plainly that no recording exists', () => {
    expect(html).toMatch(/no recording yet/i)
    expect(html).toContain('unedited capture of a real decision')
  })

  it('shows the one real frame — the workspace — with its caption', () => {
    // The recording is absent; the single frame is a real capture of the running workspace, never a
    // mock. It carries its alt, its own pixels and a `/captures/` source.
    expect(html).toContain(`src="${captures.workspace.src}"`)
    expect(html).toContain(`alt="${captures.workspace.alt}"`)
    expect(html).toContain(`width="${captures.workspace.width}"`)
    expect(html).toContain(`height="${captures.workspace.height}"`)
    expect(html).toContain(sections.open.captureCaption)
  })

  it('emits no player and no recording surface', () => {
    expect(html).not.toContain('<video')
    expect(html).not.toContain('<source')
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
