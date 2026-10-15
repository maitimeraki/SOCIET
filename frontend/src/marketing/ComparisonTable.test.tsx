import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ComparisonTable from './ComparisonTable'
import { sections } from './copy'

const html = renderToStaticMarkup(<ComparisonTable />)

describe('the comparison — a real ruled table', () => {
  it('adopts ui/Table: a thead, a tbody and the reconciliation foot', () => {
    expect(html).toContain('<table')
    expect(html).toContain('<thead')
    expect(html).toContain('<tbody')
    expect(html).toContain('<tfoot')
    expect(html).toContain(sections.comparison.reconciliation)
  })

  it('states the three approaches and the four compared columns', () => {
    for (const row of sections.comparison.rows) {
      expect(html).toContain(row.label)
      for (const cell of row.cells) expect(html).toContain(cell)
    }
    for (const column of sections.comparison.columns) expect(html).toContain(column)
  })

  it('names no competitor and measures nothing — truthful differentiators only', () => {
    // No benchmark figure and no product name beyond the three approach classes.
    expect(html).not.toMatch(/\bvs\.?\b/i)
    expect(html).not.toMatch(/\d+%/)
  })
})
