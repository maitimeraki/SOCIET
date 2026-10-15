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

/**
 * The session bootstrap, extracted so it can be exercised without a DOM. Three outcomes:
 *   - success   → adopt the user (`authed`);
 *   - 401       → a real anon: `clear()` so the guard redirects;
 *   - anything else (network, misconfig) → `unreachable`: the store stays `unknown` so the caller
 *     shows a retry, NEVER a bounce. A dead server must not read as "signed out".
 */
export async function bootstrapSession(): Promise<'authed' | 'anon' | 'unreachable'> {
  const { setUser, clear } = useAuthStore.getState()
  try {
    setUser(await authMe())
    return 'authed'
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      clear()
      return 'anon'
    }
    return 'unreachable'
  }
}
