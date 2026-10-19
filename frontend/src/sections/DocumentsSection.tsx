import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { UploadSimple } from '@phosphor-icons/react'
import { listUploads } from '../api/rest'
import type { UploadRow } from '../api/types'
import Button, { buttonClasses } from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import ErrorState from '../components/ui/ErrorState'
import Skeleton from '../components/ui/Skeleton'
import { fmtDate, fmtInt } from '../utils/format'

export interface DocumentsViewProps {
  documents: UploadRow[]
  loading: boolean
  failed: boolean
  /** The server's own failure message, when there is one; the standing copy stands in otherwise. */
  failDetail?: string
  onRetry: () => void
}

/**
 * §8.3 Documents — everything the panel argues from, presentational. The data and the retry arrive as
 * props (the default export owns the fetch), so this renders under `react-dom/server` in the node-only
 * suite where `useEffect` never fires.
 */
export function DocumentsView({ documents, loading, failed, failDetail, onRetry }: DocumentsViewProps) {
  return (
    <div className="space-y-6">
      <h1 className="font-titling text-display text-ink">Documents</h1>
      {failed ? (
        // A failure is never an empty list: it is surfaced, with a retry.
        <ErrorState
          title="Couldn't reach the server"
          detail={failDetail || 'Your documents load when the server is back.'}
          actions={
            <Button type="button" variant="secondary" onClick={onRetry}>
              Try again
            </Button>
          }
        />
      ) : loading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : documents.length === 0 ? (
        <EmptyState
          icon={<UploadSimple size={28} aria-hidden="true" />}
          line="Add your first document. Drop a PDF, paste a URL, or connect a source — everything your panel argues from comes from here."
          action={
            <Link to="/new/ingest" className={buttonClasses('primary', 40)}>
              Upload documents
            </Link>
          }
        />
      ) : (
        <ul className="divide-y divide-ink-3 border-y border-ink-3">
          {documents.map((document) => (
            <li key={document.id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-3">
              <span className="text-body text-ink">{document.name}</span>
              <span className="tnum font-measurement text-mono text-ink-3">
                Added {fmtDate(document.created_at)} · {fmtInt(document.bytes)} bytes
              </span>
              <span className="text-body text-ink-2">
                {document.read ? 'Read' : 'Not read yet'}
                {' · '}
                {document.dataset_name ? `In ${document.dataset_name}` : 'Not in a corpus yet'}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/**
 * The section's container: it owns the fetch and the retry counter the view never sees. Bumping
 * `attempt` re-runs the effect — the retry affordance without a second code path.
 */
export default function DocumentsSection() {
  const [documents, setDocuments] = useState<UploadRow[]>([])
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [failDetail, setFailDetail] = useState<string>()
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    listUploads()
      .then((page) => {
        if (cancelled) return
        setDocuments(page.items)
        setFailed(false)
        setFailDetail(undefined)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setFailed(true)
        setFailDetail(error instanceof Error ? error.message : undefined)
        setDocuments([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [attempt])

  const retry = () => {
    setLoading(true)
    setFailed(false)
    setFailDetail(undefined)
    setAttempt((n) => n + 1)
  }

  return (
    <DocumentsView
      documents={documents}
      loading={loading}
      failed={failed}
      failDetail={failDetail}
      onRetry={retry}
    />
  )
}
