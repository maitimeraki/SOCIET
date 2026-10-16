import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import TrustSection from './TrustSection'
import { sections } from './copy'

const html = renderToStaticMarkup(<TrustSection />)

describe('the trust lines — only claims the tool can keep', () => {
  it('renders every ruled line with its mark', () => {
    for (const line of sections.trust.lines) {
      expect(html).toContain(line.label)
      expect(html).toContain(line.body)
    }
  })

  it('keeps the SOC 2 line in its one legal form, marked unverified', () => {
    expect(html).toContain('SOC 2 in progress — not yet certified')
    expect(html).toContain('unverified')
  })

  it('never implies a certification that does not exist', () => {
    expect(html).not.toContain('SOC 2 certified')
    expect(html).not.toContain('SOC 2 compliant')
    expect(html).not.toContain('ISO 27001')
  })
})
