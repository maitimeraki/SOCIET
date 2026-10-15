import Button from '../components/ui/Button'
import type { AuthError } from './authRules'

/* ── the auth form's state marks ──────────────────────────────────────────────────────────────────
   The two §7.2 marks the forms render. The surface's *rules* — the security boundary (`safeNext`),
   the validators, the error copy and the stamp timing — live in `authRules.ts`; a module that exports
   components alongside plain values is exactly what `react-refresh/only-export-components` refuses,
   and these files are the first real consumers of that split. */

/**
 * §7.2 error state — a **brass caution line**, the mark in brass and the words in ink (R35). The rule
 * is drawn *above* the note: a coloured side border on an alert is the category default the craft
 * floor refuses, and brass is a symbol colour, never a text colour (2.04:1 on the sheet).
 */
export function CautionLine({ error, onRetry }: { error: AuthError; onRetry: () => void }) {
  return (
    <div role="alert" className="border-t-2 border-brass pt-2.5">
      <p className="text-body text-ink-2">{error.message}</p>
      {error.retry && (
        <Button type="button" variant="ghost" size={32} className="mt-1" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}

/**
 * §7.2 success state — the **intake stamp**: a brass impression and an ink word (R35), landing with
 * the `fix` move (a reading is taken) before the page routes on. The mark is brass; the label is ink.
 */
export function IntakeStamp({ label }: { label: string }) {
  return (
    <p role="status" className="fix inline-flex items-center gap-2 border border-brass px-3 py-2">
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" focusable="false" className="shrink-0">
        <circle cx="8" cy="8" r="6.2" fill="none" stroke="var(--color-brass)" strokeWidth="1.4" />
        <circle cx="8" cy="8" r="2.2" fill="var(--color-brass)" />
      </svg>
      <span className="text-label uppercase text-ink">{label}</span>
    </p>
  )
}
