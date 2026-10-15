import { ApiError, ConfigError, NetworkError } from '../api/rest'
import Button from '../components/ui/Button'

/* ── the auth form's shared concerns ──────────────────────────────────────────────────────────────
   Sign-in and sign-up are one surface, so the security boundary (`safeNext`), the field validators,
   the error copy and the §7.2 state marks live here, in their own module — not in `AuthLayout`, which
   owns the frame and must not own a security boundary or the form's business rules (R38). A layout is
   structure; these are the surface's rules. */

/** How long the intake stamp holds before the page routes on. Deliberate, and short: Operate users are
 *  in a task, so the stamp lands and the office opens rather than making them watch a flourish. */
export const STAMP_MS = 420

const DEFAULT_NEXT = '/dashboard'

/**
 * `next` is a security boundary. Only a same-origin, relative path is honoured: an absolute URL
 * (`https://evil`), a protocol-relative host (`//evil`), a bare relative (`runs`) or a backslash trick
 * (`/\evil`, which some engines normalise to `//`) all fall back to the dashboard — a crafted `?next=`
 * can never walk a freshly-authenticated user off-site.
 */
export function safeNext(raw: string | null | undefined): string {
  if (!raw) return DEFAULT_NEXT
  if (!raw.startsWith('/')) return DEFAULT_NEXT
  if (raw.startsWith('//')) return DEFAULT_NEXT
  if (raw.includes('\\')) return DEFAULT_NEXT
  return raw
}

export interface AuthError {
  /** The sentence shown to the user. It is honest about the failure and never reveals which field. */
  message: string
  /** A transient failure the user can retry in place (the network). A credentials failure cannot. */
  retry: boolean
}

/**
 * Map a thrown transport error to user-facing copy. Sign-in's 401 is one sentence for both fields —
 * naming the bad field would hand an attacker a username oracle — and sign-up's 409 names the taken
 * address, which the user already typed and already knows.
 */
export function authErrorCopy(error: unknown, mode: 'signin' | 'signup'): AuthError {
  if (error instanceof NetworkError) {
    return { message: "Couldn't reach the server. Check your connection and try again.", retry: true }
  }
  if (error instanceof ConfigError) {
    return { message: "This build isn't pointed at a server. Ask whoever deployed it to set it up.", retry: false }
  }
  if (error instanceof ApiError) {
    if (mode === 'signup' && error.status === 409) {
      return { message: 'That email is already registered.', retry: false }
    }
    if (error.status === 401) {
      return { message: 'Email or password is incorrect.', retry: false }
    }
    return { message: 'Something went wrong. Please try again.', retry: true }
  }
  return { message: 'Something went wrong. Please try again.', retry: true }
}

const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function emailError(value: string): string | null {
  if (value.trim() === '') return 'Enter your email address.'
  if (!EMAIL_SHAPE.test(value.trim())) return 'Enter a valid email address.'
  return null
}

export const MIN_PASSWORD = 8

export function passwordError(value: string): string | null {
  if (value === '') return 'Enter a password.'
  if (value.length < MIN_PASSWORD) return `Use at least ${MIN_PASSWORD} characters.`
  return null
}

export function confirmError(password: string, confirm: string): string | null {
  if (confirm === '') return 'Re-enter your password.'
  if (confirm !== password) return 'Passwords do not match.'
  return null
}

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
