import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { UploadSimple } from '@phosphor-icons/react'
import { listUploads } from '../api/rest'
import type { UploadRow } from '../api/types'
import { buttonClasses } from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import ErrorState from '../components/ui/ErrorState'
import { ruleClasses } from '../components/ui/Rule'
import Skeleton from '../components/ui/Skeleton'
import { DASHBOARD_COPY } from '../pages/dashboardCopy'
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
 * Your material (§14.3) — everything the panel argues from. The section's heading lives on the
 * dashboard, so this renders its content only. The data and the retry arrive as props (the default
 * export owns the fetch), so it renders under `react-dom/server` in the node-only suite where
 * `useEffect` never fires.
 */
export function DocumentsView({ documents, loading, failed, failDetail, onRetry }: DocumentsViewProps) {
  return (
    <div className="mt-6">
      {failed ? (
        // A failure is never an empty list: it is surfaced, with a retry.
        <ErrorState
          title={DASHBOARD_COPY.error.title}
          detail={failDetail || DASHBOARD_COPY.error.material}
          onRetry={onRetry}
          retryLabel={DASHBOARD_COPY.actions.retry}
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
          line={DASHBOARD_COPY.empty.material}
          action={
            <Link to="/new/ingest" className={buttonClasses('primary', 40, 'min-h-11')}>
              {DASHBOARD_COPY.actions.upload}
            </Link>
          }
        />
      ) : (
        <ul className={`${ruleClasses('around')} ${ruleClasses('both')}`}>
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

export interface DocumentsSectionProps {
  /** Bumped by the dashboard when any section's retry asks the page to refresh. */
  refreshKey?: number
  /** The page's refresh; when absent the section retries on its own. */
  onRefresh?: () => void
  /** The first read settled (success or failure) — the page may now scroll to an anchor. */
  onSettled?: () => void
}

/**
 * The section's container: it owns the fetch and the retry counter the view never sees. A retry
 * either bumps the page's refresh key (one refresh for the whole surface) or, standalone, this
 * section's own attempt.
 */
export default function DocumentsSection({
  refreshKey = 0,
  onRefresh,
  onSettled,
}: DocumentsSectionProps = {}) {
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
        setDocuments(page.items ?? [])
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
        if (cancelled) return
        setLoading(false)
        onSettled?.()
      })
    return () => {
      cancelled = true
    }
  }, [attempt, refreshKey, onSettled])

  const retry = () => {
    setLoading(true)
    setFailed(false)
    setFailDetail(undefined)
    if (onRefresh) onRefresh()
    else setAttempt((n) => n + 1)
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
