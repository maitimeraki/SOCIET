import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import TrustSection from './TrustSection'

const html = renderToStaticMarkup(<TrustSection />)

describe('trust — the mechanism and its limits, not borrowed credibility', () => {
  it('renders what the tool does', () => {
    expect(html).toContain('What it does')
    for (const label of ['It runs on your machine', 'Every claim has a source', 'Every decision is kept']) {
      expect(html).toContain(label)
    }
  })

  it('renders what the tool does not do', () => {
    expect(html).toContain('What it does not do')
    for (const label of [
      'It cannot invent a panel',
      'It does not guarantee the answer',
      'It does not keep the text from your provider',
    ]) {
      expect(html).toContain(label)
    }
  })

  it('shows no logo, testimonial or certification claim', () => {
    expect(html).not.toMatch(/SOC 2|ISO 27001/i)
    expect(html).not.toMatch(/certified|compliant/i)
    expect(html).not.toMatch(/trusted by/i)
    expect(html).not.toContain('<img')
  })

  it('names the limits plainly', () => {
    expect(html).toContain('not the truth')
    expect(html).toContain('goes to the provider you configure')
  })
})
