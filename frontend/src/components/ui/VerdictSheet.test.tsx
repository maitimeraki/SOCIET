import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import VerdictSheet from './VerdictSheet'

const sheet = (over: Partial<Parameters<typeof VerdictSheet>[0]> = {}) =>
  renderToStaticMarkup(
    <VerdictSheet
      question="Should Ridgeline Coffee open a second location on Mill Street?"
      filed="22 Oct 2026"
      position="NEGATIVE"
      share={0.82}
      caseAgainst="If the upgrade lands on time, the Mill Street economics hold."
      reasoning={['The panel divided on timing, not on the location.']}
      whoHeldWhichView={[{ position: 'NEGATIVE', names: ['Market analyst', 'Lease counsel'] }]}
      sources={[{ document: 'Mill Street lease.pdf', reference: 'p.4' }]}
      {...over}
    />,
  )

describe('the verdict sheet', () => {
  it('leads with the position, the share and the date, before any prose', () => {
    const html = sheet()
    expect(html.indexOf('Negative')).toBeLessThan(html.indexOf('The case against'))
    expect(html.indexOf('0.82')).toBeLessThan(html.indexOf('The case against'))
    expect(html.indexOf('22 Oct 2026')).toBeLessThan(html.indexOf('The case against'))
  })

  it('gives the case against its own ruled block', () => {
    const html = sheet()
    expect(html).toContain('The case against')
    expect(html).toContain('border-l-3')
    expect(html).toContain('border-caution')
  })

  it('sets the figure in mono and never colours it by position', () => {
    const html = sheet()
    expect(html).toContain('font-mono')
    expect(html).not.toContain('text-neg')
  })

  it('names who held which view in words', () => {
    const html = sheet()
    expect(html).toContain('Market analyst')
    expect(html).toContain('Lease counsel')
  })
})
