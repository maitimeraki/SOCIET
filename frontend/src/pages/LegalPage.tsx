import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, legalDocument } from '../api/rest'
import type { LegalDocument } from '../api/types'
import { inlineLinkClasses } from '../components/ui/Button'
import ErrorState from '../components/ui/ErrorState'
import Skeleton from '../components/ui/Skeleton'
import { fmtDay } from '../utils/format'

/**
 * §7 The legal surface. The text is Task 9's registry content, served as written: this page renders
 * it, it does not author it. The copy law is exempt on these routes only (see `test/copyLaw.ts`) —
 * statutory wording may name the machinery, and rewriting it here would drift from the served
 * version whose hash a consent record points at.
 */

/** The title is the document's first markdown heading; the rest is body, untouched. */
// eslint-disable-next-line react-refresh/only-export-components -- a pure splitter shared with its test, not a component
export function splitLegalContent(content: string): { title: string; body: string } {
  const lines = content.split('\n')
  const heading = lines.findIndex((line) => /^#{1,6}\s+\S/.test(line))
  if (heading < 0) return { title: '', body: content }
  const title = lines[heading].replace(/^#{1,6}\s+/, '').trim()
  const body = [...lines.slice(0, heading), ...lines.slice(heading + 1)].join('\n').replace(/^\n+/, '')
  return { title, body }
}

/** A 404 is the registry saying "no such slug"; every other failure is the server being unreachable. */
// eslint-disable-next-line react-refresh/only-export-components -- a pure mapping shared with its test, not a component
export const isNotFoundError = (error: unknown): boolean =>
  error instanceof ApiError && error.status === 404

export interface LegalPageViewProps {
  doc: LegalDocument | null
  loading: boolean
  failed: boolean
  /** A 404 from the registry is a friendly dead end, not the server-error state. */
  notFound?: boolean
  onRetry?: () => void
}

const COLUMN = 'mx-auto w-[min(760px,calc(100%-48px))]'
const BACK_LINK = `${inlineLinkClasses} font-ui text-body-sm text-ink-2 underline underline-offset-4 hover:text-ink`

export function LegalPageView({ doc, loading, failed, notFound = false, onRetry }: LegalPageViewProps) {
  return (
    <div className="min-h-screen bg-bone py-14">
      <div className={COLUMN}>
        <Link to="/legal" className={BACK_LINK}>
          All legal documents
        </Link>

        {loading ? (
          <div className="mt-8" aria-busy="true">
            <Skeleton className="h-10 w-2/3" />
            <Skeleton className="mt-4 h-4 w-1/3" />
            <div className="mt-10 space-y-3">
              {[0, 1, 2, 3, 4, 5, 6, 7].map((index) => (
                <Skeleton key={index} className="h-4 w-full" />
              ))}
            </div>
          </div>
        ) : notFound ? (
          <div className="mt-10 border-l-[3px] border-rule bg-paper py-3 pl-3.5">
            <p className="text-body-sm font-semibold text-ink">That document isn't here.</p>
            <p className="mt-1 max-w-[60ch] text-body-sm text-ink-2">
              The address may be mistyped, or the document may have been renamed.
            </p>
          </div>
        ) : failed || !doc ? (
          <div className="mt-10">
            <ErrorState
              title="Couldn't reach the server"
              detail="The documents are still in force; nothing was lost."
              onRetry={onRetry}
              retryLabel="Try again"
            />
          </div>
        ) : (
          <article className="mt-8">
            <h1 className="font-display text-display font-medium tracking-[-0.03em] text-ink">
              {splitLegalContent(doc.content).title || doc.slug}
            </h1>
            <p className="mt-3 font-mono text-micro uppercase tracking-[0.08em] text-ink-3">
              Version {doc.version} &middot; Effective {fmtDay(doc.effective_at)}
            </p>
            <div className="mt-8 whitespace-pre-wrap font-ui text-body leading-[28px] text-ink-2">
              {splitLegalContent(doc.content).body}
            </div>
          </article>
        )}
      </div>
    </div>
  )
}

export default function LegalPage({ slug: fixedSlug }: { slug?: string }) {
  const { slug: routeSlug } = useParams()
  // Keyed so a move between `/legal/{a}` and `/legal/{b}` starts from a fresh fetch, never from the
  // previous document's state.
  return <LegalDocument key={fixedSlug ?? routeSlug ?? ''} slug={fixedSlug ?? routeSlug ?? ''} />
}

function LegalDocument({ slug }: { slug: string }) {
  const [doc, setDoc] = useState<LegalDocument | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [notFound, setNotFound] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    legalDocument(slug)
      .then((payload) => {
        if (!cancelled) setDoc(payload)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setDoc(null)
        if (isNotFoundError(error)) setNotFound(true)
        else setFailed(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [slug, attempt])

  const retry = () => {
    setLoading(true)
    setFailed(false)
    setNotFound(false)
    setAttempt((value) => value + 1)
  }

  return <LegalPageView doc={doc} loading={loading} failed={failed} notFound={notFound} onRetry={retry} />
}
