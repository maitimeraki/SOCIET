import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { UploadRow } from '../api/types'
import { BANNED_WORD, renderedText } from '../test/copyLaw'
import { DocumentsPageView, type DocumentsPageViewProps } from './DocumentsPage'

afterEach(() => vi.unstubAllGlobals())

const doc = (patch: Partial<UploadRow> = {}): UploadRow => ({
  id: 'u1',
  name: 'market-research.pdf',
  bytes: 20480,
  mime: 'application/pdf',
  read: true,
  dataset_id: 'ds-1',
  dataset_name: 'Europe expansion',
  created_at: '2026-10-01T10:00:00Z',
  ...patch,
})

const render = (props: Partial<DocumentsPageViewProps> = {}) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <DocumentsPageView
        documents={[]}
        loading={false}
        failed={false}
        selected={null}
        onSelect={() => {}}
        onClose={() => {}}
        onRetry={() => {}}
        {...props}
      />
    </MemoryRouter>,
  )

describe('DocumentsPageView', () => {
  it('renders the four column headings and a document row', () => {
    const html = render({ documents: [doc()] })
    expect(html).toContain('Document')
    expect(html).toContain('Corpus')
    expect(html).toContain('Added')
    expect(html).toContain('State')
    expect(html).toContain('market-research.pdf')
    expect(html).toContain('Europe expansion')
    expect(html).toContain('1 Oct 2026 10:00')
    expect(html).toContain('Read')
  })

  it('names the single next action when empty', () => {
    const html = render({ documents: [] })
    expect(html).toContain('Upload documents')
    expect(html).toContain('/new?step=ingest')
  })

  it('renders a real failure with a retry, never an empty list', () => {
    const html = render({ documents: [], failed: true })
    expect(html).toContain('reach the server')
    expect(html).toContain('Try again')
    expect(html).not.toContain('Upload documents')
  })

  it('carries no banned word in loaded, empty or failed state', () => {
    expect(renderedText(render({ documents: [doc()] }))).not.toMatch(BANNED_WORD)
    expect(renderedText(render({ documents: [] }))).not.toMatch(BANNED_WORD)
    expect(renderedText(render({ documents: [], failed: true }))).not.toMatch(BANNED_WORD)
  })
})
