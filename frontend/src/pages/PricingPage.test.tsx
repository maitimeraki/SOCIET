import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo: render to static markup in Node. MemoryRouter is
// required because the page's header and actions are `<Link>`s — React Router throws outside one.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import PricingPage from './PricingPage'
import { BANNED_TERMS, renderedText } from '../test/copyLaw'

const render = () =>
  renderToStaticMarkup(
    <MemoryRouter>
      <PricingPage />
    </MemoryRouter>,
  )

describe('the plans', () => {
  it('names the three plan lines, with no popularity claim', () => {
    const html = render()
    expect(html).toContain('Starter')
    expect(html).toContain('Studio')
    expect(html).toContain('Enterprise')
    expect(html).not.toContain('Desk')
    expect(html).not.toContain('Most chosen')
  })

  it('states units per month, panel size and passes per decision — and no material volume', () => {
    const html = render()
    expect(html).toContain('Units / month')
    expect(html).toContain('8,000')
    expect(html).toContain('16,000')
    expect(html).toContain('Panel size')
    expect(html).toContain('Passes per decision')
    expect(html).not.toContain('MB')
    expect(html).not.toContain('GB')
    expect(html).not.toMatch(/corpus/i)
    expect(html).not.toContain('decision / month')
    expect(html).not.toContain('Local-first')
  })

  it('renders no banned word', () => {
    expect(renderedText(render())).not.toMatch(BANNED_TERMS)
  })

  it('keeps the enterprise mailto and the 44px targets', () => {
    const html = render()
    const open = [...html.matchAll(/<a\b[^>]*>/g)].map((match) => match[0]).find((tag) => tag.includes('href="/overview"'))
    expect(open).toContain('min-h-11')
    expect(html).toContain('mailto:hello@societas.app?subject=Enterprise%20plan')
    expect(html).not.toContain('societas.example')
    // Anonymous visitors get the signup door, never a checkout control.
    expect(html).toContain('href="/auth/signup?next=/pricing"')
  })
})
