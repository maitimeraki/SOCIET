import { Link, Outlet } from 'react-router-dom'
import { ApiError, ConfigError, NetworkError } from '../api/rest'
import Legend, { type LegendEntry } from '../components/common/Legend'
import StanceSymbol from '../components/common/StanceSymbol'
import Button from '../components/ui/Button'

/* ── the auth surface's shared parts ──────────────────────────────────────────────────────────────
   Sign-in and sign-up are one surface, so the security boundary (`safeNext`), the field validators
   and the error copy live here, in the surface's own module, rather than in each page — a duplicated
   `safeNext` would be a duplicated redirect boundary. Task 15b's scope is three files, so this is the
   single source of truth rather than a fourth shared module. */

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

/** The legend law (§3/§9): the three stations in the sample are keyed, symbol + word, so the hue is
 *  never the only carrier. Reuses the surface's own glyphs rather than redrawing them. */
const SAMPLE_LEGEND: LegendEntry[] = [
  { key: 'POS', symbol: <StanceSymbol stance="POSITIVE" />, label: 'positive' },
  { key: 'NEU', symbol: <StanceSymbol stance="NEUTRAL" />, label: 'neutral' },
  { key: 'NEG', symbol: <StanceSymbol stance="NEGATIVE" />, label: 'negative' },
]

/**
 * §7.2's "small honest sample of the sheet": three stations, their lines of sight, and the fix, drawn
 * in the sheet's own geometry (a graticule, station marks matching `StanceSymbol`'s stroke weights, a
 * brass-ringed fix). It is captioned as a sample, never a run — no fabricated result. The `fix` ring
 * is drawn here, not imported from `FixMark`, whose one-mark-owns-the-word law reserves it for verdict
 * surfaces; this is a labelled illustration, and it is `aria-hidden` behind its caption.
 */
function SampleSheet() {
  return (
    <figure className="mt-10">
      <svg viewBox="0 0 260 150" className="w-full" aria-hidden="true" focusable="false">
        {/* graticule — the sheet's own datum hairlines */}
        <g stroke="var(--color-datum-dim)" strokeWidth="0.5" opacity="0.45">
          <line x1="0" y1="38" x2="260" y2="38" />
          <line x1="0" y1="76" x2="260" y2="76" />
          <line x1="0" y1="114" x2="260" y2="114" />
          <line x1="65" y1="0" x2="65" y2="150" />
          <line x1="130" y1="0" x2="130" y2="150" />
          <line x1="195" y1="0" x2="195" y2="150" />
        </g>
        {/* lines of sight between the stations */}
        <g stroke="var(--color-ink-4)" strokeWidth="0.9">
          <line x1="64" y1="44" x2="176" y2="96" />
          <line x1="176" y1="96" x2="104" y2="122" />
          <line x1="104" y1="122" x2="64" y2="44" />
        </g>
        {/* three stations — the same drawn forms as the legend key */}
        <polygon points="64,35 74,52 54,52" fill="var(--color-stance-pos)" />
        <g fill="none" stroke="var(--color-stance-neu)" strokeWidth="1.5">
          <rect x="169" y="89" width="14" height="14" />
          <path d="M169 96h14M176 89v14" />
        </g>
        <path
          d="M97 115 111 129M111 115 97 129"
          fill="none"
          stroke="var(--color-stance-neg)"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        {/* the fix — an ink ring, a brass centre, the plotted point */}
        <circle cx="124" cy="70" r="12" fill="none" stroke="var(--color-ink)" strokeWidth="1.5" />
        <circle cx="124" cy="70" r="3.8" fill="var(--color-brass)" />
        <circle cx="133" cy="61" r="2.4" fill="var(--color-route)" />
      </svg>
      <figcaption className="mt-3 font-measurement text-mono text-ink-3">
        A sample sheet, not a run — three stations, their lines of sight, and the fix.
      </figcaption>
      <Legend className="mt-3" entries={SAMPLE_LEGEND} title="Stations" />
    </figure>
  )
}

/**
 * §7.2 Authentication — the survey office's front door. A single intake form on the sheet (left) and a
 * quiet ruled half-sheet (right) stating the thesis once and showing a sample of the sheet, so the
 * page belongs to the world. `<main>` landmark, the wordmark in Archivo caps, and **no shell chrome**:
 * a visitor who has not signed in gets no app navigation.
 *
 * It is a layout route: the form itself is the `<Outlet/>` (SignInPage / SignUpPage), so the frame is
 * built once and the two pages differ only in their fields.
 */
export default function AuthLayout() {
  return (
    <main className="min-h-screen bg-survey-paper">
      <div className="mx-auto grid min-h-screen w-full max-w-6xl grid-cols-1 lg:grid-cols-2">
        <div className="flex flex-col px-6 py-10 sm:px-10 lg:px-14">
          <Link to="/" className="inline-flex items-baseline gap-2.5 self-start">
            <span className="font-titling text-[18px] uppercase leading-none tracking-[0.08em] text-ink">Societas</span>
            <span className="hidden font-measurement text-mono uppercase tracking-[0.06em] text-ink-3 sm:inline">
              Survey &amp; deliberation
            </span>
          </Link>
          <div className="mt-14 w-full max-w-sm">
            <Outlet />
          </div>
        </div>

        {/* Stacks below the form under `lg` rather than disappearing: the sheet is how the page
            belongs to the world (§7.2), and §9 keeps the hierarchy while it drops columns. */}
        <aside className="border-t border-ink-4 px-6 py-12 sm:px-10 lg:flex lg:flex-col lg:justify-center lg:border-l lg:border-t-0 lg:px-14 lg:py-16">
          <p className="max-w-[26ch] font-titling text-title text-ink">
            A society of specialists measures a decision into a publishable sheet.
          </p>
          <SampleSheet />
        </aside>
      </div>
    </main>
  )
}
