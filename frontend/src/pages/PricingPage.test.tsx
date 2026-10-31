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
  it('names exactly two metered units', () => {
    const html = render()
    expect(html).toContain('Corpus size')
    expect(html).toContain('Deep decisions')
    // R12 — no per-seat pricing. The copy's deliberate "No seats." is not a metered unit.
    expect(html).not.toMatch(/per[- ]seat/i)
    expect(html).toContain('No seats.')
  })

  it('shows two plans and one custom band', () => {
    const html = render()
    expect(html).toContain('Desk')
    expect(html).toContain('Studio')
    expect(html).toContain('Most chosen')
    expect(html).toContain('A standing panel, or a corpus that keeps growing.')
  })

  it('has no calculator, no slider and no annual toggle', () => {
    const html = render()
    expect(html).not.toContain('type="range"')
    expect(html).not.toContain('Annual')
    expect(html).not.toContain('Save 20')
  })

  it('renders no banned word', () => {
    expect(renderedText(render())).not.toMatch(BANNED_TERMS)
  })
})
