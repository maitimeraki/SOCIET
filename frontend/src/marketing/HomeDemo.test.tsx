import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo: render to static markup in Node.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { BANNED_TERMS, renderedText } from '../test/copyLaw'
import HomeDemo from './HomeDemo'

const html = renderToStaticMarkup(
  <MemoryRouter>
    <HomeDemo />
  </MemoryRouter>,
)

describe('the /demo-home marketing page', () => {
  it('renders no banned word', () => {
    expect(renderedText(html)).not.toMatch(BANNED_TERMS)
  })

  it('makes no local-first or free-tier claim', () => {
    const text = renderedText(html)
    expect(text).not.toMatch(/local-first|runs on the machine|machine you start/i)
    expect(text).not.toMatch(/free to use|no card, no tier|no tier|most chosen/i)
  })

  it('reaches every legal document from the footer', () => {
    for (const href of ['/privacy', '/terms', '/refund', '/legal/subprocessors']) {
      expect(html).toContain(`href="${href}"`)
    }
  })
})
