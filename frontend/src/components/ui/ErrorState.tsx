import type { ReactNode } from 'react'
import Button from './Button'

/**
 * §6 The error state: a real message, the server's own detail when there is one, and — when the
 * caller can recover — the retry. The retry is the primitive's, so every failing surface offers
 * the same affordance in the same place (§14.3's ERROR row). `actions` still carries any extra
 * control a surface needs beside it.
 */
export default function ErrorState({
  title,
  detail,
  actions,
  onRetry,
  retryLabel = 'Try again',
}: {
  title: string
  detail?: string
  actions?: ReactNode
  onRetry?: () => void
  retryLabel?: string
}) {
  return (
    <div className="border-t border-ink-3 pt-5">
      <p className="text-heading text-ink">{title}</p>
      {detail && <p className="mt-2 max-w-[60ch] text-body text-ink-2">{detail}</p>}
      {(actions || onRetry) && (
        <div className="mt-4 flex items-center gap-3">
          {actions}
          {onRetry && (
            <Button type="button" variant="secondary" onClick={onRetry}>
              {retryLabel}
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
