import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import RecordSheet from './RecordSheet'

const html = renderToStaticMarkup(<RecordSheet />)

describe('the record — the shape of a filed decision, not a fabricated sample', () => {
  it('says plainly that this is not a sample decision', () => {
    expect(html).toMatch(/not a sample decision/i)
    expect(html).toContain('no invented answer, no borrowed source')
  })

  it('shows every field the filed document holds', () => {
    expect(html).toContain('Decision · filed')
    expect(html).toContain('What the document holds')
    for (const label of ['The answer', 'The opposing case', 'The positions', 'The sources', 'The passes']) {
      expect(html).toContain(label)
    }
  })

  it('invents no answer, number, source or screenshot', () => {
    expect(html).not.toContain('<img')
    expect(html).not.toContain('<figure')
    expect(html).not.toMatch(/\b0\.\d+\b/)
    expect(html).not.toMatch(/\d+%/)
    expect(html).not.toContain('EU Trade Brief')
    expect(html).not.toContain('Market Sizing')
    expect(html).not.toContain('Data-Readiness Note')
  })

  it('states that the record is kept and reopens as it ended', () => {
    expect(html).toContain('Kept, not summarised')
    expect(html).toContain('reopens as it ended')
  })
})
