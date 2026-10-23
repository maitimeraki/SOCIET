import { ApiError, ConfigError, NetworkError } from '../api/rest'

/* ── the auth surface's rules ─────────────────────────────────────────────────────────────────────
   Sign-in and sign-up are one surface, so the security boundary (`safeNext`), the field validators,
   the error copy and the §7.2 timing constant live here, in their own pure module. The components that
   render them — `CautionLine`, `IntakeStamp` — live in `authForm.tsx` and consume this module; the
   frame lives in `AuthLayout` (R38). A layout is structure; these are the surface's rules. */

/** How long the intake stamp holds before the page routes on. The `plot-fix` move it rides runs 560 ms
 *  and only reaches full opacity at 60% (~336 ms), so a shorter hold was a blink on a normal-motion
 *  machine. 640 ms lets the mark complete (560 ms) and settle for a beat before the page moves on. */
export const STAMP_MS = 640

const DEFAULT_NEXT = '/dashboard'

/**
 * Tab, newline, CR and the rest of the C0/C1 controls. The WHATWG URL parser *strips* these anywhere
 * in the input, so `/\n/evil.example` would otherwise normalise to `//evil.example` → an off-site
 * origin. Rejecting them outright closes that class before any parsing happens.
 *
 * A character-code scan rather than a regex: the same set (0x00–0x1f, 0x7f) without a control-char
 * pattern, which `no-control-regex` refuses by design.
 */
function hasControlChars(value: string): boolean {
  for (const char of value) {
    const code = char.charCodeAt(0)
    if (code <= 0x1f || code === 0x7f) return true
  }
  return false
}

/**
 * `next` is a security boundary. Only a same-origin, relative path is honoured: an absolute URL
 * (`https://evil`), a protocol-relative host (`//evil`), a bare relative (`runs`), a backslash trick
 * (`/\evil`, which some engines normalise to `//`) or a value carrying a stripped control character
 * (`/\n/evil.example`) all fall back to the dashboard — a crafted `?next=` can never walk a
 * freshly-authenticated user off-site.
 *
 * Two layers: the syntactic guards above reject the known shapes, then the value is resolved against
 * the app origin and must stay on it (defence in depth against an unforeseen normalisation). `location`
 * does not exist under the node test runner, so the fallback base is required.
 */
export function safeNext(raw: string | null | undefined): string {
  if (!raw) return DEFAULT_NEXT
  if (hasControlChars(raw)) return DEFAULT_NEXT
  if (!raw.startsWith('/')) return DEFAULT_NEXT
  if (raw.startsWith('//')) return DEFAULT_NEXT
  if (raw.includes('\\')) return DEFAULT_NEXT
  const base = globalThis.location?.origin ?? 'http://localhost'
  try {
    if (new URL(raw, base).origin !== base) return DEFAULT_NEXT
  } catch {
    return DEFAULT_NEXT
  }
  return raw
}

/** The other door's carried destination — `safeNext` runs before anything enters the URL. */
export function nextSuffix(params: URLSearchParams): string {
  const next = params.get('next')
  return next ? `?next=${encodeURIComponent(safeNext(next))}` : ''
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
 * The invalid mark for one field: **derived from the field's current value, on every render**.
 *
 * `touched` says *when* the mark first appears — on blur, or on submit — and the field's own value
 * says *whether* it is there. So the mark clears the moment that field's value becomes valid, a
 * paste or an autofill as much as a keystroke, and a submit does not leave the other fields red
 * while one of them is being corrected.
 *
 * It is a function of the value rather than stored state on purpose: a stored flag can only be
 * cleared by a keystroke in that field, which is the cascade bug §14.2 names.
 */
export function fieldProblem(
  value: string,
  touched: boolean,
  submitted: boolean,
  validate: (value: string) => string | null,
): string | null {
  if (!touched && !submitted) return null
  return validate(value)
}
