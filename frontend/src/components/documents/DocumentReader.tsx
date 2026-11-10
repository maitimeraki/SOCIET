import { useEffect, useRef } from 'react'
import { X } from '@phosphor-icons/react'
import IconButton from '../ui/IconButton'
import Skeleton from '../ui/Skeleton'

export interface DocumentReaderViewProps {
  title: string
  meta: string
  text: string
  loading?: boolean
  failed?: boolean
  onClose: () => void
  onRetry?: () => void
}

export function DocumentReaderView({
  title,
  meta,
  text,
  loading = false,
  failed = false,
  onClose,
  onRetry,
}: DocumentReaderViewProps) {
  const panel = useRef<HTMLElement>(null)

  // The reader is opened from a row, so it takes focus on mount and gives it back on close (the page
  // does that). `useEffect` never runs during a static render, so this stays SSR-safe.
  useEffect(() => {
    panel.current?.focus()
  }, [])

  return (
    <aside
      ref={panel}
      tabIndex={-1}
      aria-label="Document"
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.stopPropagation()
          onClose()
        }
      }}
      // §7.4 — paper on the sheet shadow: a 480px right sheet on desktop, a full-screen sheet on
      // the phone. The surface declares itself once, so no border rides beside the shadow.
      className="fixed inset-0 z-50 overflow-y-auto bg-paper p-5 lg:bottom-auto lg:left-auto lg:right-6 lg:top-24 lg:z-40 lg:h-[calc(100vh-8rem)] lg:w-[480px] lg:rounded-lg lg:p-6 lg:shadow-sheet"
    >
      <div className="flex items-start justify-between gap-3 border-b border-hairline pb-3">
        <div className="min-w-0">
          <p className="font-mono text-micro uppercase tracking-[0.08em] text-ink-3">Document</p>
          <h2 className="mt-1 font-display text-heading text-ink">{title}</h2>
          <p className="mt-1 font-mono text-micro text-ink-3">{meta}</p>
        </div>
        <IconButton label="Close document" onClick={onClose}>
          <X size={18} aria-hidden="true" />
        </IconButton>
      </div>
      {loading ? (
        <Skeleton className="mt-3 h-40 w-full" />
      ) : failed ? (
        <div className="mt-3">
          <p className="font-ui text-body text-ink-2">This document could not be read.</p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-2 min-h-11 font-ui text-body text-accent hover:text-accent-hover"
            >
              Try again
            </button>
          )}
        </div>
      ) : (
        <p className="mt-4 max-w-[68ch] whitespace-pre-line font-ui text-body text-ink-2">{text}</p>
      )}
    </aside>
  )
}

export default DocumentReaderView
