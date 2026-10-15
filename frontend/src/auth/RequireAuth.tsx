import { useEffect, useState } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { ApiError, authMe } from '../api/rest'
import Button from '../components/ui/Button'
import Skeleton from '../components/ui/Skeleton'
import { useAuthStore, type AuthStatus } from './authStore'

/* ── the guard ────────────────────────────────────────────────────────────────────────────────────
   A layout-route element. It owns the session bootstrap (`GET /api/v1/auth/me` had no caller before
   this task) and the decision it drives. The headline rule: a returning user is NEVER shown the
   sign-in page while their cookie is still being checked, and a user whose session is merely
   *unreachable* is never bounced — only a real 401 is an anon. */

/** The guard's decision, as a pure function so the three states are pinned without a router. */
export type GuardDecision = 'splash' | 'redirect' | 'outlet'

export function resolveGuard(status: AuthStatus): GuardDecision {
  if (status === 'authed') return 'outlet'
  if (status === 'anon') return 'redirect'
  return 'splash' // `unknown`: still resolving — splash, never a redirect
}

/** Where an `anon` visitor is sent, carrying the path (and search) they were reaching for. The value
 *  is `encodeURIComponent`d so `?next=` cannot smuggle a second query or a fragment; `safeNext`
 *  (authForm) is the other half of the boundary and validates it again on the way back. */
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

/**
 * The `unknown` state: a full-page splash while the session resolves. It is announced (a live status
 * region) and carries no sign-in form — the whole point is that a returning user sees a skeleton, not
 * a login page. When the check failed without a verdict (`unreachable`), it offers a keyboard-operable
 * retry instead of a redirect.
 */
export function AuthSplash({ unreachable, onRetry }: { unreachable: boolean; onRetry: () => void }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-5 bg-survey-paper px-6 text-center">
      <div role="status" aria-live="polite" className="flex w-full max-w-sm flex-col gap-3">
        <span className="sr-only">Checking your session…</span>
        <Skeleton className="h-7 w-52" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
      </div>
      {unreachable && (
        <div className="flex max-w-sm flex-col items-center gap-3">
          <p className="text-body text-ink-2">
            We couldn't reach the server to check your session. Nothing is lost — try again.
          </p>
          <Button type="button" variant="secondary" onClick={onRetry}>
            Try again
          </Button>
        </div>
      )}
    </div>
  )
}

/**
 * The guard's render, split from the store read so its three states are testable under SSR: zustand
 * v5's server snapshot returns the INITIAL state, so a store-driven render always reads `unknown` and
 * cannot be asserted. Everything here is a prop; `RequireAuth` supplies them from the store.
 */
export function GuardView({
  status,
  target,
  unreachable,
  onRetry,
}: {
  status: AuthStatus
  target: string
  unreachable: boolean
  onRetry: () => void
}) {
  const decision = resolveGuard(status)
  if (decision === 'outlet') return <Outlet />
  if (decision === 'redirect') return <Navigate to={target} replace />
  return <AuthSplash unreachable={unreachable} onRetry={onRetry} />
}

export default function RequireAuth() {
  const status = useAuthStore((s) => s.status)
  const { pathname, search } = useLocation()
  const [unreachable, setUnreachable] = useState(false)
  // Bumping this re-runs the bootstrap effect — the retry affordance without a second code path.
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (status !== 'unknown') return
    let cancelled = false
    void bootstrapSession().then((outcome) => {
      if (!cancelled && outcome === 'unreachable') setUnreachable(true)
    })
    return () => {
      cancelled = true
    }
  }, [status, attempt])

  return (
    <GuardView
      status={status}
      target={signInTarget(pathname, search)}
      unreachable={unreachable}
      onRetry={() => {
        setUnreachable(false)
        setAttempt((n) => n + 1)
      }}
    />
  )
}
