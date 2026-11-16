import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ReportDocument from './ReportDocument'
import type { ReportModel } from './exportReport'
import { BANNED_TERMS, renderedText } from '../../test/copyLaw'

const PRODUCED: ReportModel = {
  title: 'Expand into Europe?',
  reportStatus: 'produced',
  markdown: '# Expand into Europe?\n## Recommendation\nPosition: POSITIVE, 83%, settled\nExpand, cautiously.',
  sources: { '1': { document: 'EU market study 2026', section: 'Tariffs' } },
  warnings: ['The demand study is a proxy.'],
}

const NOT_PRODUCED: ReportModel = {
  title: null,
  reportStatus: 'not_produced',
  markdown: null,
  sources: {},
  warnings: [],
}

const render = (report: ReportModel) =>
  renderToStaticMarkup(<ReportDocument report={report} runId="r1" onRestored={() => Promise.resolve()} />)

describe('a produced report', () => {
  it('renders the markdown as given, with no retry offered', () => {
    const html = render(PRODUCED)
    expect(html).toContain('Expand, cautiously.')
    expect(html).not.toContain('Report not produced')
    expect(html).not.toContain('Retry report')
  })

  it('lists the run’s warnings under their own heading', () => {
    const html = render(PRODUCED)
    expect(html).toContain('The demand study is a proxy.')
    expect(html).toContain('Warnings')
  })
})

describe('a report that was not produced', () => {
  it('says so, offers the one retry, and shows no markdown', () => {
    const html = render(NOT_PRODUCED)
    expect(html).toContain('Report not produced')
    expect(html).toContain('Retry report')
    expect(html).not.toContain('Recommendation')
  })

  it('branches on the status: no text is shown for it, and a retry is offered, whatever text a stray field holds', () => {
    const html = render({ ...NOT_PRODUCED, markdown: 'Stray text.' })
    expect(html).not.toContain('Stray text.')
    expect(html).toContain('Retry report')
  })

  it('shows no warnings section when there are none', () => {
    expect(render(NOT_PRODUCED)).not.toContain('Warnings')
  })

  it('carries no banned word', () => {
    expect(renderedText(render(NOT_PRODUCED))).not.toMatch(BANNED_TERMS)
  })
})
