import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { legalDocuments } from '../api/rest'
import type { LegalDocumentMeta } from '../api/types'
import ErrorState from '../components/ui/ErrorState'
import Skeleton from '../components/ui/Skeleton'
import { LEGAL_LINKS } from '../config/legalLinks'
import { fmtDay } from '../utils/format'

/**
 * §7 The index behind `/legal`: every published document, its version and effective date, and the
 * way in. The footer links reach the same routes directly; this page is the complete list.
 */
const COLUMN = 'mx-auto w-[min(760px,calc(100%-48px))]'

const labelFor = (slug: string) =>
  LEGAL_LINKS.find((link) => link.href === slug || link.href.endsWith(`/${slug}`))?.label ?? slug

export interface LegalIndexViewProps {
  documents: LegalDocumentMeta[]
  loading: boolean
  failed: boolean
  onRetry?: () => void
}

export function LegalIndexView({ documents, loading, failed, onRetry }: LegalIndexViewProps) {
  return (
    <div className="min-h-screen bg-bone py-14">
      <div className={COLUMN}>
        <Link to="/" className="font-ui text-body-sm text-ink-2 underline underline-offset-4 hover:text-ink">
          Back to Societas
        </Link>
        <h1 className="mt-6 font-display text-display font-medium tracking-[-0.03em] text-ink">
          Legal documents
        </h1>
        <p className="mt-3 max-w-[56ch] font-ui text-body text-ink-2">
          The terms that apply to the service, and the providers behind it, as currently published.
        </p>

        <nav aria-label="Legal documents" className="mt-10">
          {loading ? (
            <div className="space-y-3">
              {[0, 1, 2, 3].map((index) => (
                <Skeleton key={index} className="h-14 w-full" />
              ))}
            </div>
          ) : failed ? (
            <ErrorState
              title="Couldn't reach the server"
              detail="The documents are still in force; nothing was lost."
              onRetry={onRetry}
              retryLabel="Try again"
            />
          ) : (
            <ul className="border-t border-rule">
              {documents.map((document) => (
                <li key={document.slug} className="border-b border-rule">
                  <Link
                    to={`/legal/${document.slug}`}
                    className="flex min-h-14 flex-wrap items-baseline justify-between gap-3 py-4 font-ui text-body text-ink hover:text-accent"
                  >
                    <span>{labelFor(document.slug)}</span>
                    <span className="font-mono text-micro uppercase tracking-[0.06em] text-ink-3">
                      Version {document.version} &middot; Effective {fmtDay(document.effective_at)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </nav>
      </div>
    </div>
  )
}

export default function LegalIndexPage() {
  const [documents, setDocuments] = useState<LegalDocumentMeta[]>([])
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    legalDocuments()
      .then((payload) => {
        if (!cancelled) setDocuments(payload)
      })
      .catch(() => {
        if (cancelled) return
        setDocuments([])
        setFailed(true)
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
    setAttempt((value) => value + 1)
  }

  return <LegalIndexView documents={documents} loading={loading} failed={failed} onRetry={retry} />
}
