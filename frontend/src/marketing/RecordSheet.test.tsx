import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import RecordSheet from './RecordSheet'
import { sections } from './copy'

const html = renderToStaticMarkup(<RecordSheet />)

describe('the record — a finished run as a sheet', () => {
  it('labels the sample synthetic, so it is never read as a live run', () => {
    expect(html).toContain(sections.record.syntheticLabel)
  })

  it('shows the fix, its confidence and the closure figure', () => {
    expect(html).toContain(sections.record.verdictWord)
    expect(html).toContain(sections.record.confidence.toFixed(2))
    expect(html).toContain(`closure ${sections.record.closure}`)
  })

  it('keeps the dissent and prints the contents map back to the record', () => {
    expect(html).toContain(sections.record.dissentLabel)
    expect(html).toContain(sections.record.dissent)
    expect(html).toContain(sections.record.contentsLabel)
    for (const row of sections.record.contents) {
      expect(html).toContain(row.entity)
      expect(html).toContain(row.source)
    }
  })

  it('holds a labelled slot for the Task 19 capture — no fabricated screenshot', () => {
    expect(html).toContain(sections.record.captureLabel)
    expect(html).not.toContain('<img')
  })
})
