import { create } from 'zustand'
import { authLogin, authLogout, authSignup, registerUnauthorizedHandler } from '../api/rest'
import type { User } from '../api/types'

/** `unknown` until `GET /auth/me` resolves — the guard must never flash the login page before then. */
export type AuthStatus = 'unknown' | 'anon' | 'authed'

export interface AuthStoreState {
  status: AuthStatus
  user: User | null
  /** Adopt a session minted elsewhere (the `me` bootstrap, or a successful sign-in/up). */
  setUser: (user: User) => void
  /** Drop the session locally: `anon` + no user. Called by sign-out and the 401 seam. */
  clear: () => void
  signin: (email: string, password: string) => Promise<void>
  signup: (email: string, password: string) => Promise<void>
  signout: () => Promise<void>
}

export const useAuthStore = create<AuthStoreState>((set, get) => ({
  status: 'unknown',
  user: null,

  setUser: (user) => set({ status: 'authed', user }),
  clear: () => set({ status: 'anon', user: null }),

  signin: async (email, password) => {
    const user = await authLogin(email, password) // throws ApiError(401) on bad credentials
    set({ status: 'authed', user })
  },

  signup: async (email, password) => {
    const user = await authSignup(email, password) // throws ApiError(409) on a taken email
    set({ status: 'authed', user })
  },

  signout: async () => {
    try {
      await authLogout()
    } catch {
      // Best-effort server logout: a dead server must not trap the user in a signed-in UI. The
      // local clear below is authoritative; if the cookie outlives it, the next request 401s and
      // the seam clears again.
    } finally {
      get().clear()
    }
  },
}))

// The 401 seam: `rest.ts` invokes this on any 401. This is the ONLY edge between the two modules —
// `rest.ts` never imports the store, so there is no cycle.
registerUnauthorizedHandler(() => useAuthStore.getState().clear())
