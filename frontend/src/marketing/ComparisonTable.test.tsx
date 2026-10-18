import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ComparisonTable from './ComparisonTable'

const html = renderToStaticMarkup(<ComparisonTable />)

describe('the comparison — mechanisms, not vendors', () => {
  it('adopts ui/Table with a reconciliation foot', () => {
    expect(html).toContain('<table')
    expect(html).toContain('<thead')
    expect(html).toContain('<tbody')
    expect(html).toContain('<tfoot')
    expect(html).toContain('not what any other product does')
  })

  it('states the two mechanisms and every compared row', () => {
    for (const column of ['A single answer', 'A panel decision']) expect(html).toContain(column)
    for (const row of [
      'Who forms the view',
      'What a claim rests on',
      'What happens to disagreement',
      'What confidence means',
      'What you keep',
    ]) {
      expect(html).toContain(row)
    }
  })

  it('names no third party, measures nothing, and says it is not a vendor comparison', () => {
    expect(html).not.toMatch(/\bvs\.?\b/i)
    expect(html).not.toMatch(/\d+%/)
    expect(html).not.toMatch(/chatbot|assistant/i)
    expect(html).toContain('No third-party capability is claimed or measured')
  })
})
