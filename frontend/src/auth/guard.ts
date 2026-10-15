import { ApiError, authMe } from '../api/rest'
import { useAuthStore, type AuthStatus } from './authStore'

/* ── the guard's decision logic ───────────────────────────────────────────────────────────────────
   The session bootstrap and the decision it drives, split from the components that render them
   (`RequireAuth.tsx`) so they are pure and DOM-free. The headline rule: a returning user is NEVER
   shown the sign-in page while their cookie is still being checked, and a user whose session is
   merely *unreachable* is never bounced — only a real 401 is an anon. */

/** The guard's decision, as a pure function so the three states are pinned without a router. */
export type GuardDecision = 'splash' | 'redirect' | 'outlet'

export function resolveGuard(status: AuthStatus): GuardDecision {
  if (status === 'authed') return 'outlet'
  if (status === 'anon') return 'redirect'
  return 'splash' // `unknown`: still resolving — splash, never a redirect
}

/** Where an `anon` visitor is sent, carrying the path (and search) they were reaching for. The value
 *  is `encodeURIComponent`d so `?next=` cannot smuggle a second query or a fragment; `safeNext`
 *  (authRules) is the other half of the boundary and validates it again on the way back. */
export function signInTarget(pathname: string, search: string): string {
  return `/auth/signin?next=${encodeURIComponent(pathname + search)}`
}

/** `rest.ts`'s fetch carries no timeout, so a proxy that accepts `/api/v1/auth/me` and never answers
 *  would leave the guard on `unknown` forever — an infinite splash with no retry and no sign-in link.
 *  Cap the wait so a hung check reads as a network failure instead of never settling. */
export const SESSION_CHECK_TIMEOUT_MS = 10_000

/** Race the call against the timeout; the loser is drained so a late settle never dangles. */
function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined
  const timedOut = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error('session check timed out')), timeoutMs)
  })
  promise.catch(() => {}) // a rejection after the timeout won must not be unhandled
  return Promise.race([promise, timedOut]).finally(() => clearTimeout(timer))
}

/**
 * The session bootstrap, extracted so it can be exercised without a DOM. Three outcomes:
 *   - success   → adopt the user (`authed`);
 *   - 401       → a real anon: `clear()` so the guard redirects;
 *   - anything else (network, misconfig, timeout) → `unreachable`: the store stays `unknown` so the
 *     caller shows a retry, NEVER a bounce. A dead or hung server must not read as "signed out".
 * `timeoutMs` is injectable so the timeout path can be tested without a 10-second wait.
 */
export async function bootstrapSession(
  timeoutMs: number = SESSION_CHECK_TIMEOUT_MS,
): Promise<'authed' | 'anon' | 'unreachable'> {
  const { setUser, clear } = useAuthStore.getState()
  try {
    setUser(await withTimeout(authMe(), timeoutMs))
    return 'authed'
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      clear()
      return 'anon'
    }
    return 'unreachable'
  }
}
