import { useEffect, useRef } from 'react'
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
      className="mt-6 border-t border-rule pt-4 lg:fixed lg:right-6 lg:top-24 lg:z-40 lg:mt-0 lg:h-[calc(100vh-8rem)] lg:w-[480px] lg:overflow-y-auto lg:rounded-lg lg:bg-canvas lg:p-6 lg:shadow-overlay"
    >
      <div className="flex items-start justify-between gap-3 border-b border-rule/50 pb-3">
        <div>
          <p className="font-measurement text-micro text-ink-3">DOCUMENT</p>
          <p className="text-body text-ink">{title}</p>
          <p className="mt-1 font-measurement text-micro text-ink-3">{meta}</p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close document" className="min-h-11 text-body text-ink-3 hover:text-ink">
          Close
        </button>
      </div>
      {loading ? (
        <Skeleton className="mt-3 h-40 w-full" />
      ) : failed ? (
        <div className="mt-3">
          <p className="text-body text-ink-2">This document could not be read.</p>
          {onRetry && (
            <button type="button" onClick={onRetry} className="mt-2 min-h-11 text-body text-accent hover:text-accent">
              Try again
            </button>
          )}
        </div>
      ) : (
        <p className="mt-3 max-w-[68ch] whitespace-pre-line font-record text-body-lg text-ink-2">{text}</p>
      )}
    </aside>
  )
}

export default DocumentReaderView
