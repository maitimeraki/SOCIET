import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { UploadRow } from '../api/types'
import { BANNED_TERMS, renderedText } from '../test/copyLaw'
import { DocumentsPageView, type DocumentsPageViewProps } from './DocumentsPage'

afterEach(() => vi.unstubAllGlobals())

const doc = (patch: Partial<UploadRow> = {}): UploadRow => ({
  id: 'u1',
  name: 'market-research.pdf',
  bytes: 2_400_000,
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
  it('renders the five column headings and a document row', () => {
    const html = render({ documents: [doc()] })
    expect(html).toContain('Name')
    expect(html).toContain('Added')
    expect(html).toContain('Size')
    expect(html).toContain('Read')
    expect(html).toContain('Corpus')
    expect(html).toContain('market-research.pdf')
    expect(html).toContain('Europe expansion')
    expect(html).toContain('1 Oct 2026 10:00')
  })

  it('names the single next action when empty', () => {
    const html = render({ documents: [] })
    expect(html).toContain('Start with your material')
    expect(html).toContain('Everything else follows from it.')
    expect(html).toContain('Add your first document')
    expect(html).toContain('/new?step=ingest')
  })

  it('renders a real failure with a retry, never an empty list', () => {
    const html = render({ documents: [], failed: true })
    expect(html).toContain('reach the server')
    expect(html).toContain('Try again')
    expect(html).not.toContain('Add your first document')
  })

  it('carries no banned word in loaded, empty or failed state', () => {
    expect(renderedText(render({ documents: [doc()] }))).not.toMatch(BANNED_TERMS)
    expect(renderedText(render({ documents: [] }))).not.toMatch(BANNED_TERMS)
    expect(renderedText(render({ documents: [], failed: true }))).not.toMatch(BANNED_TERMS)
  })

  it('renders the reader when a document is selected', () => {
    const html = render({
      documents: [doc()],
      selected: {
        document: doc({ bytes: 840_000 }),
        text: 'The lease renews for a further five years.',
        loading: false,
        failed: false,
      },
    })
    expect(html).toContain('The lease renews for a further five years.')
    expect(html).toContain('840 KB')
    expect(html).toContain('Close document')
  })
})

describe('the documents table', () => {
  it('is a ruled table, not a card grid', () => {
    const html = render({
      documents: [doc({ id: 'u1', name: 'Mill Street lease.pdf', dataset_name: 'Mill Street expansion', read: true })],
    })
    expect(html).toContain('<table')
    expect(html).toContain('Mill Street expansion')
    expect(html).toContain('2 MB')
    expect(html).toContain('>Read</th>')
    expect(html).not.toContain('border-l')
  })

  it('says the read state in words, never in colour alone', () => {
    const html = render({ documents: [doc({ id: 'u2', read: false })] })
    expect(html).toContain('Reading')
  })

  it('measures a small file in KB rather than zero megabytes', () => {
    const html = render({ documents: [doc({ id: 'u3', bytes: 480_000 })] })
    expect(html).toContain('480 KB')
  })

  it('stacks each row as label/value pairs below md, and keeps the ruled table at md+', () => {
    const html = render({ documents: [doc()] })
    for (const label of ['Name', 'Added', 'Size', 'Read', 'Corpus']) {
      expect(html, label).toContain(`data-label="${label}"`)
    }
    expect(html).toContain('md:table-row')
    expect(html).toContain('md:table-header-group')
    // §10.2 — no horizontal scroll means no fixed-width row; every cell is a block below md.
    expect(html).toContain('block py-1.5')
  })

  it('draws record boundaries on the record rule, never the decorative hairline', () => {
    expect(render({ documents: [doc()] })).not.toContain('border-rule/40')
  })
})
