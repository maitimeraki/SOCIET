import { useEffect, useState } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import Button from '../components/ui/Button'
import Skeleton from '../components/ui/Skeleton'
import { useAuthStore, type AuthStatus } from './authStore'
import { bootstrapSession, resolveGuard, signInTarget } from './guard'

/* ── the guard's components ───────────────────────────────────────────────────────────────────────
   A layout-route element and the two surfaces it renders. The decision logic and the session
   bootstrap live in `guard.ts`; this module renders them. */

/**
 * The `unknown` state: a full-page splash while the session resolves. It is announced (a live status
 * region) and carries no sign-in form — the whole point is that a returning user sees a skeleton, not
 * a login page. When the check failed without a verdict (`unreachable`), it offers a keyboard-operable
 * retry instead of a redirect.
 */
export function AuthSplash({ unreachable, onRetry }: { unreachable: boolean; onRetry: () => void }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-5 bg-bone px-6 text-center">
      {/* One live region owns BOTH the waiting copy and the failure copy, so the flip to `unreachable`
          — the failure text plus the retry — is what a screen reader announces, not just "Checking…".
          The skeletons carry no announcement (Skeleton is aria-hidden), so they can stay put. */}
      <div
        role="status"
        aria-live="polite"
        className="flex w-full max-w-sm flex-col items-center gap-3"
      >
        {!unreachable && <span className="sr-only">Checking your session…</span>}
        <Skeleton className="h-7 w-52" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
        {unreachable && (
          <>
            <p className="text-body text-ink-2">
              We couldn't reach the server to check your session. Nothing is lost — try again.
            </p>
            <Button type="button" variant="secondary" onClick={onRetry}>
              Try again
            </Button>
          </>
        )}
      </div>
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
