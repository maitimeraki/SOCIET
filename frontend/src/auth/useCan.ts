import type { Role, User } from '../api/types'
import { useAuthStore } from './authStore'

/** The pure role check: a missing user holds no role. */
export function can(user: User | null, ...roles: Role[]): boolean {
  return user !== null && roles.includes(user.role)
}

/** The store-bound role check — UX only; the API re-checks every request. */
export function useCan(...roles: Role[]): boolean {
  return useAuthStore((s) => can(s.user, ...roles))
}
