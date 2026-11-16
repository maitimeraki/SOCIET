import { describe, expect, it } from 'vitest'
import { reportHtml, reportJson, reportMarkdown } from './exportReport'
import type { ReportModel } from './exportReport'

const MARKDOWN = [
  '# Should Ridgeline Coffee open a second location?',
  '## Recommendation',
  'Position: NEGATIVE, 82%, settled',
  'Point: The Mill Street economics hold [2] (from the documents)',
  'Point: Timing matters more than place (judgement)',
].join('\n')

const REPORT: ReportModel = {
  title: 'Should Ridgeline Coffee open a second location?',
  reportStatus: 'produced',
  markdown: MARKDOWN,
  sources: {
    '2': { document: 'Mill Street study', section: 'Footfall' },
    '1': { document: 'Grease-trap permit', section: '' },
  },
  warnings: ['The demand study is a proxy.'],
}

describe('the export is the markdown as given, then the sources it cites', () => {
  it('writes the markdown unchanged and a plain Sources list in citation order', () => {
    expect(reportMarkdown(REPORT)).toBe(
      `${MARKDOWN}\n\n## Sources\n\n- [1] Grease-trap permit\n- [2] Mill Street study — Footfall\n`,
    )
  })

  it('adds no section the backend did not write when there are no sources', () => {
    expect(reportMarkdown({ ...REPORT, sources: {} })).toBe(`${MARKDOWN}\n`)
  })

  it('exports nothing for a report that was not produced', () => {
    expect(reportMarkdown({ ...REPORT, reportStatus: 'not_produced', markdown: null, sources: {} })).toBe('')
  })

  it('never carries an id: the sources are the public document and section', () => {
    const out = reportMarkdown(REPORT)
    expect(out).not.toMatch(/chunk|node|evidence|[0-9a-f]{8}-[0-9a-f]{4}/i)
  })
})

describe('the HTML export reads the same blocks and escapes customer text', () => {
  it('renders the title, sections, points and the Sources list', () => {
    const html = reportHtml(REPORT)
    expect(html).toContain('<h1>Should Ridgeline Coffee open a second location?</h1>')
    expect(html).toContain('<h2>Recommendation</h2>')
    expect(html).toContain('<h2>Sources</h2>')
    expect(html).toContain('[2] Mill Street study — Footfall')
  })

  it('escapes markup in the report and its sources', () => {
    const html = reportHtml({
      ...REPORT,
      title: '<script>alert(1)</script>',
      markdown: '# <script>alert(1)</script>\nRent < 4,200 & rising > 3% (from the documents)',
      sources: { '1': { document: '<img src=x onerror=alert(1)>', section: '' } },
    })
    expect(html).not.toContain('<script>')
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
    expect(html).toContain('Rent &lt; 4,200 &amp; rising &gt; 3%')
  })
})

describe('the JSON export is the model, with the same document as a string', () => {
  it('carries the status, title, markdown, sources and the document', () => {
    const json = JSON.parse(reportJson(REPORT))
    expect(json.reportStatus).toBe('produced')
    expect(json.title).toBe(REPORT.title)
    expect(json.sources).toEqual(REPORT.sources)
    expect(json.document).toBe(reportMarkdown(REPORT))
  })
})
