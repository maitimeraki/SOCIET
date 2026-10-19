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

  it('shows the real workspace frame with its caption', () => {
    // The recording is absent; the workspace is one of the section's two real frames (the other is
    // the opposing case under stage 3), never a mock. It carries its alt, its own pixels and a
    // `/captures/` source.
    expect(html).toContain(`src="${captures.workspace.src}"`)
    expect(html).toContain(`alt="${captures.workspace.alt}"`)
    expect(html).toContain(`width="${captures.workspace.width}"`)
    expect(html).toContain(`height="${captures.workspace.height}"`)
    expect(html).toContain(sections.open.captureCaption)
  })

  it('shows the real map under stage 2, with its caption', () => {
    const mapFrame = html.match(/<figure[^>]*data-capture="map"[\s\S]*?<\/figure>/)?.[0] ?? ''
    expect(mapFrame).toContain(`src="${captures.map.src}"`)
    expect(mapFrame).toContain(`alt="${captures.map.alt}"`)
    expect(mapFrame).toContain(`width="${captures.map.width}"`)
    expect(mapFrame).toContain(`height="${captures.map.height}"`)
    expect(mapFrame).toContain(sections.open.mapCaption)
    // It follows the stage whose claim it shows and precedes the filed answer.
    expect(html.indexOf('data-capture="map"')).toBeGreaterThan(html.indexOf('The panel, arguing in passes'))
    expect(html.indexOf('data-capture="case"')).toBeGreaterThan(html.indexOf('data-capture="map"'))
    expect(html.indexOf('data-capture="workspace"')).toBeGreaterThan(html.indexOf('data-capture="map"'))
  })

  it('files the opposing case under stage 3, as a real frame with its caption', () => {
    const caseFrame = html.match(/<figure[^>]*data-capture="case"[\s\S]*?<\/figure>/)?.[0] ?? ''
    expect(caseFrame).toContain(`src="${captures.opposingCase.src}"`)
    expect(caseFrame).toContain(`alt="${captures.opposingCase.alt}"`)
    expect(caseFrame).toContain(`width="${captures.opposingCase.width}"`)
    expect(caseFrame).toContain(`height="${captures.opposingCase.height}"`)
    expect(caseFrame).toContain(sections.open.caseCaption)
    // It follows the stage whose claim it shows.
    expect(html.indexOf('data-capture="case"')).toBeGreaterThan(html.indexOf('The answer, filed with its case'))
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
