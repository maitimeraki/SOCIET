import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { BANNED_WORD, renderedText } from '../../test/copyLaw'
import { DocumentReaderView } from './DocumentReader'

describe('DocumentReaderView', () => {
  it('shows the title, meta, text and a close control', () => {
    const html = renderToStaticMarkup(
      <DocumentReaderView
        title="Mill Street lease — 2026.pdf"
        meta="Added 12 Oct 2026 · 184,320 bytes · Mill Street"
        text="The lease renews for a further five years."
        onClose={() => {}}
      />,
    )
    expect(html).toContain('Mill Street lease — 2026.pdf')
    expect(html).toContain('184,320')
    expect(html).toContain('The lease renews for a further five years.')
    expect(html).toContain('Close')
  })

  it('renders a loading skeleton and a failed message', () => {
    const loading = renderToStaticMarkup(
      <DocumentReaderView title="x" meta="y" text="" loading onClose={() => {}} />,
    )
    expect(loading).toContain('animate-pulse')
    const failed = renderToStaticMarkup(
      <DocumentReaderView title="x" meta="y" text="" failed onClose={() => {}} />,
    )
    expect(failed).toContain('could not be read')
  })

  it('carries no banned word', () => {
    expect(
      renderedText(
        renderToStaticMarkup(<DocumentReaderView title="x" meta="y" text="The record." onClose={() => {}} />),
      ),
    ).not.toMatch(BANNED_WORD)
    expect(
      renderedText(renderToStaticMarkup(<DocumentReaderView title="x" meta="y" text="" failed onClose={() => {}} />)),
    ).not.toMatch(BANNED_WORD)
  })
})
