import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import DemoVideo from './DemoVideo'
import { sections } from './copy'

const html = renderToStaticMarkup(<DemoVideo />)

describe('the field recording — the honest empty state', () => {
  it('never emits a broken player or a fabricated mp4', () => {
    // The asset does not exist, so the poster branch renders and no <video> (and no 404) is emitted.
    expect(html).not.toContain('<video')
    expect(html).not.toContain('.mp4')
    expect(html).not.toContain('<source')
  })

  it('shows the labelled poster and its honest caption', () => {
    expect(html).toContain(sections.demo.poster)
    expect(html).toContain(sections.demo.plateCaption)
  })

  it('frames the recording and offers the transcript disclosure', () => {
    expect(html).toContain(sections.demo.frameLabel)
    expect(html).toContain('<details')
    expect(html).toContain(sections.demo.transcriptLabel)
  })
})
