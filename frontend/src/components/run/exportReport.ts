import type { ReportSource, ReportSources, ReportStatus } from '../../run/events'
import { narrowSources } from '../../run/reducer'
import { inlineParts, reportBlocks } from './reportBlocks'

/**
 * The filed report as the page and every export read it. `markdown` is the backend's text, as
 * written; the client adds no section, heading or fallback of its own. Sources carry the public
 * document and section only: no chunk, node or evidence id ever reaches this model.
 */
export interface ReportModel {
  title: string | null
  reportStatus: ReportStatus
  markdown: string | null
  sources: ReportSources
  warnings: string[]
}

/** Citation entries in citation order. */
function orderedSources(sources: ReportSources): [string, ReportSource][] {
  return Object.entries(narrowSources(sources)).sort(([a], [b]) => Number(a) - Number(b))
}

const sourceLabel = (source: ReportSource): string =>
  source.section ? `${source.document} — ${source.section}` : source.document

/** The markdown as given, then a plain Sources list for the `[n]` markers in it. */
export function reportMarkdown(report: ReportModel): string {
  if (report.markdown === null) return ''
  const body = report.markdown.trimEnd()
  const sources = orderedSources(report.sources).map(([n, source]) => `- [${n}] ${sourceLabel(source)}`)
  return sources.length > 0 ? `${body}\n\n## Sources\n\n${sources.join('\n')}\n` : `${body}\n`
}

export function reportHtml(report: ReportModel): string {
  const escape = (value: string) =>
    value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const inline = (text: string) =>
    inlineParts(text)
      .map((part) => {
        const html = escape(part.kind === 'source' ? part.raw : part.text)
        return part.strong ? `<strong>${html}</strong>` : html
      })
      .join('')
  const body = (report.markdown === null ? [] : reportBlocks(report.markdown))
    .map((block) => {
      switch (block.kind) {
        case 'title':
          return `<h1>${escape(block.text)}</h1>`
        case 'heading':
          return `<h2>${escape(block.text)}</h2>`
        case 'paragraph':
          return `<p>${inline(block.text)}</p>`
        case 'list':
          return `<ul>${block.items.map((item) => `<li>${inline(item)}</li>`).join('')}</ul>`
      }
    })
    .join('')
  const sources = orderedSources(report.sources)
  const sourceList =
    sources.length > 0
      ? `<h2>Sources</h2><ul>${sources.map(([n, source]) => `<li>[${escape(n)}] ${escape(sourceLabel(source))}</li>`).join('')}</ul>`
      : ''
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${escape(report.title ?? 'Decision report')}</title></head><body>${body}${sourceList}</body></html>`
}

/** The model, as data, with the same document as a readable string. */
export function reportJson(report: ReportModel): string {
  return JSON.stringify({ ...report, sources: narrowSources(report.sources), document: reportMarkdown(report) }, null, 2)
}
