import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { getIngestDocuments, listUploads } from '../api/rest'
import type { UploadRow } from '../api/types'
import { DocumentReaderView } from '../components/documents/DocumentReader'
import { buttonClasses } from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import ErrorState from '../components/ui/ErrorState'
import Skeleton from '../components/ui/Skeleton'
import { fmtBytes, fmtDate, fmtInt } from '../utils/format'

export interface DocumentsPageViewProps {
  documents: UploadRow[]
  loading: boolean
  failed: boolean
  failDetail?: string
  selected: { document: UploadRow; text: string; loading: boolean; failed: boolean } | null
  onSelect: (document: UploadRow) => void
  onClose: () => void
  onRetry: () => void
}

const readerMeta = (document: UploadRow) =>
  `Added ${fmtDate(document.created_at)} · ${fmtBytes(document.bytes)} · ${document.dataset_name ?? 'Not in a corpus yet'}`

/** §10.2 — below md each row is a stack of label/value pairs; at md and up it is the ruled table. */
const STACK_CELL = 'block py-1.5 md:table-cell md:py-0 md:pr-3'
const STACK_LABEL = 'mb-1 block font-ui text-label uppercase tracking-[0.08em] text-ink-3 md:hidden'

export function DocumentsPageView({
  documents,
  loading,
  failed,
  failDetail,
  selected,
  onSelect,
  onClose,
  onRetry,
}: DocumentsPageViewProps) {
  const read = documents.filter((document) => document.read).length
  const corpora = new Set(documents.map((document) => document.dataset_name).filter(Boolean)).size

  return (
    <div>
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-rule pb-6">
        <div>
          <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Documents</p>
          <h1 className="font-display text-display font-medium tracking-[-0.03em] text-ink">Your material</h1>
          <p className="mt-2 max-w-[60ch] font-ui text-body-sm text-ink-2">Everything your panel argues from.</p>
        </div>
        <Link to="/new?step=ingest" className={buttonClasses('primary', 48, 'min-h-11')}>
          Add documents
        </Link>
      </header>

      <p className="mb-3 font-mono text-micro text-ink-3">
        {fmtInt(documents.length)} DOCUMENTS &middot; {fmtInt(read)} READ &middot; {fmtInt(corpora)} CORPORA
      </p>

      {failed ? (
        <ErrorState
          title="Couldn't reach the server"
          detail={failDetail || 'Nothing was lost.'}
          onRetry={onRetry}
          retryLabel="Try again"
        />
      ) : loading ? (
        <div>
          {[0, 1, 2, 3, 4].map((index) => (
            <Skeleton key={index} className="h-[52px] w-full" />
          ))}
        </div>
      ) : documents.length === 0 ? (
        <EmptyState
          title="Start with your material"
          line="Everything else follows from it."
          action={
            <Link to="/new?step=ingest" className={buttonClasses('primary', 40, 'min-h-11')}>
              Add your first document
            </Link>
          }
        />
      ) : (
        <table className="w-full border-collapse">
          <thead className="hidden md:table-header-group">
            <tr>
              {['Name', 'Added', 'Size', 'Read', 'Corpus'].map((heading) => (
                <th
                  key={heading}
                  scope="col"
                  className={`border-b border-rule px-0 pb-2 font-ui text-label uppercase tracking-[0.08em] text-ink-3 ${
                    heading === 'Added' || heading === 'Size' ? 'text-right' : 'text-left'
                  }`}
                >
                  {heading}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="block md:table-row-group">
            {documents.map((document) => (
              <tr
                key={document.id}
                onClick={() => onSelect(document)}
                className="block cursor-pointer border-b border-rule py-3 hover:bg-accent-soft md:table-row md:h-[52px] md:py-0"
              >
                <td data-label="Name" className={`${STACK_CELL} font-ui text-body-sm text-ink`}>
                  <span className={STACK_LABEL}>Name</span>
                  <button
                    type="button"
                    data-document-id={document.id}
                    onClick={(event) => {
                      event.stopPropagation()
                      onSelect(document)
                    }}
                    className="min-h-11 text-left font-ui text-body-sm font-medium text-ink"
                  >
                    {document.name}
                  </button>
                </td>
                <td
                  data-label="Added"
                  className={`${STACK_CELL} font-mono text-mono text-ink-3 md:text-right`}
                >
                  <span className={STACK_LABEL}>Added</span>
                  {fmtDate(document.created_at)}
                </td>
                <td
                  data-label="Size"
                  className={`${STACK_CELL} font-mono text-mono text-ink-3 md:text-right`}
                >
                  <span className={STACK_LABEL}>Size</span>
                  {fmtBytes(document.bytes)}
                </td>
                <td data-label="Read" className="block py-1.5 md:table-cell md:py-0">
                  <span className={STACK_LABEL}>Read</span>
                  {document.read ? (
                    <span className="inline-flex min-h-6 items-center gap-1.5 rounded-xs bg-accent-soft px-2 font-mono text-micro uppercase tracking-[0.04em] text-ok">
                      <i className="h-1.5 w-1.5 rounded-full bg-ok" aria-hidden="true" />Read
                    </span>
                  ) : (
                    <span className="inline-flex min-h-6 items-center gap-1.5 rounded-xs bg-sand px-2 font-mono text-micro uppercase tracking-[0.04em] text-ink-2">
                      <i className="h-1.5 w-1.5 rounded-full bg-ink-3" aria-hidden="true" />Reading
                    </span>
                  )}
                </td>
                <td data-label="Corpus" className={`${STACK_CELL} font-ui text-body-sm text-ink-2`}>
                  <span className={STACK_LABEL}>Corpus</span>
                  {document.dataset_name ?? 'Not in a corpus yet'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selected && (
        <DocumentReaderView
          title={selected.document.name}
          meta={readerMeta(selected.document)}
          text={selected.text}
          loading={selected.loading}
          failed={selected.failed}
          onClose={onClose}
          onRetry={() => onSelect(selected.document)}
        />
      )}
    </div>
  )
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<UploadRow[]>([])
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [failDetail, setFailDetail] = useState<string>()
  const [attempt, setAttempt] = useState(0)
  const [selected, setSelected] = useState<DocumentsPageViewProps['selected']>(null)
  // Every selection or close bumps the token; a late resolution from an older request is ignored
  // so it can neither revert the reader to the previous document nor re-open a closed one.
  const requestRef = useRef(0)

  useEffect(() => {
    let cancelled = false
    listUploads()
      .then((page) => {
        if (cancelled) return
        setDocuments(page.items ?? [])
        setFailed(false)
        setFailDetail(undefined)
      })
      .catch(() => {
        if (cancelled) return
        setFailed(true)
        // The server's raw text is not customer copy — the view's curated fallback renders instead.
        setFailDetail(undefined)
        setDocuments([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [attempt])

  const reload = () => {
    setLoading(true)
    setFailed(false)
    setFailDetail(undefined)
    setAttempt((value) => value + 1)
  }

  // One read path for selection and for the reader's retry, so a retry cannot show a different
  // document or race a newer open.
  const open = (document: UploadRow) => {
    const request = ++requestRef.current
    setSelected({ document, text: '', loading: true, failed: false })
    void getIngestDocuments([document.id])
      .then(({ documents: payload }) => {
        if (requestRef.current !== request) return
        const text = payload[0]?.text ?? ''
        setSelected({ document, text, loading: false, failed: false })
      })
      .catch(() => {
        if (requestRef.current !== request) return
        setSelected({ document, text: '', loading: false, failed: true })
      })
  }

  return (
    <DocumentsPageView
      documents={documents}
      loading={loading}
      failed={failed}
      failDetail={failDetail}
      selected={selected}
      onSelect={open}
      onClose={() => {
        const id = selected?.document.id
        requestRef.current += 1
        setSelected(null)
        // §15.2 — the row is the trigger, so focus goes back to it once the reader has closed.
        if (!id || typeof document === 'undefined' || typeof requestAnimationFrame !== 'function') return
        requestAnimationFrame(() => {
          document.querySelector<HTMLElement>(`[data-document-id="${id}"]`)?.focus()
        })
      }}
      onRetry={reload}
    />
  )
}
