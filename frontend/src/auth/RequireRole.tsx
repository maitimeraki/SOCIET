import type { ReactNode } from 'react'
import type { Role } from '../api/types'
import ForbiddenPage from '../pages/ForbiddenPage'
import { useAuthStore } from './authStore'

/**
 * The role guard's render, split from the store read so it is testable under SSR — zustand v5's
 * server snapshot returns the INITIAL state, so a store-driven render can only ever read `null`.
 * A denied visitor or a missing role renders the 403 page; there is never a sign-in redirect.
 */
export function RoleGuardView({
  role,
  roles,
  children,
}: {
  role: Role | null
  roles: Role[]
  children: ReactNode
}) {
  if (role === null || !roles.includes(role)) return <ForbiddenPage />
  return <>{children}</>
}

export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const role = useAuthStore((s) => s.user?.role ?? null)
  return (
    <RoleGuardView role={role} roles={roles}>
      {children}
    </RoleGuardView>
  )
}
