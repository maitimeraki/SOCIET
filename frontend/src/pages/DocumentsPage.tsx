import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { getIngestDocuments, listUploads } from '../api/rest'
import type { UploadRow } from '../api/types'
import { DocumentReaderView } from '../components/documents/DocumentReader'
import { buttonClasses } from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import ErrorState from '../components/ui/ErrorState'
import Skeleton from '../components/ui/Skeleton'
import { fmtDate, fmtInt } from '../utils/format'

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
  `Added ${fmtDate(document.created_at)} · ${fmtInt(document.bytes)} bytes · ${document.dataset_name ?? 'Not in a corpus yet'}`

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
          <h1 className="font-titling text-display text-ink">Documents</h1>
          <p className="mt-2 max-w-[60ch] text-body text-ink-2">
            Everything you've provided, and what has been read of it.
          </p>
        </div>
        <Link to="/new?step=ingest" className={buttonClasses('secondary', 40, 'min-h-11')}>
          Add material
        </Link>
      </header>

      <p className="mb-2 font-measurement text-micro text-ink-3">
        {fmtInt(documents.length)} DOCUMENTS · {fmtInt(read)} READ · {fmtInt(corpora)} CORPORA
      </p>

      {failed ? (
        <ErrorState
          title="Couldn't reach the server"
          detail={failDetail || 'Your documents load when the server is back.'}
          onRetry={onRetry}
          retryLabel="Try again"
        />
      ) : loading ? (
        <div className="space-y-2">
          {[0, 1, 2, 3].map((index) => (
            <Skeleton key={index} className="h-12 w-full" />
          ))}
        </div>
      ) : documents.length === 0 ? (
        <EmptyState
          line="Add your first document. Everything your panel argues from comes from here."
          action={
            <Link to="/new?step=ingest" className={buttonClasses('primary', 40, 'min-h-11')}>
              Upload documents
            </Link>
          }
        />
      ) : (
        <table className="w-full border-collapse">
          <thead>
            <tr>
              {['Document', 'Corpus', 'Added', 'State'].map((heading) => (
                <th
                  key={heading}
                  scope="col"
                  className="border-b border-rule px-0 pb-2 text-left font-measurement text-[8px] uppercase tracking-[0.12em] text-ink-3"
                >
                  {heading}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {documents.map((document) => (
              <tr
                key={document.id}
                onClick={() => onSelect(document)}
                className="cursor-pointer border-b border-rule/40 hover:bg-ground-2"
              >
                <td className="py-3 pr-3 text-body text-ink">
                  <button
                    type="button"
                    data-document-id={document.id}
                    onClick={(event) => {
                      event.stopPropagation()
                      onSelect(document)
                    }}
                    className="min-h-11 text-left text-body text-ink"
                  >
                    {document.name}
                  </button>
                </td>
                <td className="py-3 pr-3 text-body text-ink-2">{document.dataset_name ?? 'Not in a corpus yet'}</td>
                <td className="py-3 pr-3 font-measurement text-mono text-ink-3">{fmtDate(document.created_at)}</td>
                <td className="py-3 font-measurement text-micro text-ink-2">
                  {document.read ? '● Read' : '○ Not read yet'}
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
