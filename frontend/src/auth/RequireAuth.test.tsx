import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): components are rendered
// to static markup in Node. `<Navigate>` does not navigate under SSR, so the router-level redirect is
// pinned through `resolveGuard`/`signInTarget` here and covered end-to-end by Task 19's run.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { useAuthStore, type AuthStatus } from './authStore'
import { bootstrapSession, resolveGuard, signInTarget } from './guard'
import { AuthSplash, GuardView } from './RequireAuth'

const USER = { id: 'u1', email: 'a@b.c', created_at: '2026-01-01T00:00:00Z' }

beforeEach(() => useAuthStore.setState({ status: 'unknown', user: null }))
afterEach(() => vi.unstubAllGlobals())

/** The guard's render at a deep path + search, so the redirect target has both to preserve. Rendered
 *  through `GuardView` (a prop) rather than the store: zustand v5's SSR snapshot is the initial
 *  state, so a store-driven render could only ever be asserted as `unknown`. */
function renderGuard(status: AuthStatus) {
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={['/runs/abc?tab=log']}>
      <Routes>
        <Route
          element={
            <GuardView status={status} target={signInTarget('/runs/abc', '?tab=log')} unreachable={false} onRetry={() => {}} />
          }
        >
          <Route path="/runs/:runId" element={<p>guarded child</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('resolveGuard — the three states', () => {
  it('unknown → splash, never a redirect (no login flash while the session resolves)', () => {
    expect(resolveGuard('unknown')).toBe('splash')
  })

  it('anon → redirect', () => {
    expect(resolveGuard('anon')).toBe('redirect')
  })

  it('authed → outlet', () => {
    expect(resolveGuard('authed')).toBe('outlet')
  })
})

describe('signInTarget — the redirect target', () => {
  it('preserves the encoded path + search as ?next=', () => {
    expect(signInTarget('/runs/abc', '?tab=log')).toBe(
      '/auth/signin?next=' + encodeURIComponent('/runs/abc?tab=log'),
    )
  })

  it('encodes a bare path so `next` cannot smuggle a second query', () => {
    expect(signInTarget('/a/b', '')).toBe('/auth/signin?next=%2Fa%2Fb')
  })
})

describe('GuardView — rendered states', () => {
  it('renders its child when authed', () => {
    expect(renderGuard('authed')).toContain('guarded child')
  })

  it('renders the splash — not a sign-in page — while the session is unknown', () => {
    const html = renderGuard('unknown')
    expect(html).toContain('Checking your session')
    expect(html).not.toContain('guarded child')
  })

  it('renders no child for anon (the redirect is a Navigate, which does not fire under SSR)', () => {
    const html = renderGuard('anon')
    expect(html).not.toContain('guarded child')
    expect(html).not.toContain('Checking your session')
  })
})

describe('AuthSplash — the unknown state', () => {
  it('announces the check and shows no retry while it is resolving', () => {
    const html = renderToStaticMarkup(<AuthSplash unreachable={false} onRetry={() => {}} />)
    expect(html).toContain('role="status"')
    expect(html).toContain('Checking your session')
    expect(html).not.toContain('Try again')
  })

  it('offers a labelled, keyboard-operable retry — never a redirect — when unreachable', () => {
    const html = renderToStaticMarkup(<AuthSplash unreachable onRetry={() => {}} />)
    expect(html).toContain('Try again')
    expect(html).toMatch(/<button/)
    expect(html).not.toContain('auth/signin')
  })

  it('announces the failure inside the live region — the retry is inside role="status", not beside it', () => {
    const html = renderToStaticMarkup(<AuthSplash unreachable onRetry={() => {}} />)
    // The waiting copy is gone (so the region's text actually flips), and the failure copy + retry
    // come after the live region opens — i.e. inside it, so both are announced.
    expect(html).not.toContain('Checking your session')
    expect(html).toContain('reach the server to check your session')
    expect(html.indexOf('role="status"')).toBeLessThan(html.indexOf('Try again'))
    expect(html.indexOf('role="status"')).toBeLessThan(html.indexOf('reach the server to check your session'))
  })
})

describe('bootstrapSession — the three outcomes', () => {
  it('adopts the session on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(USER), { status: 200 })))

    await expect(bootstrapSession()).resolves.toBe('authed')

    expect(useAuthStore.getState()).toMatchObject({ status: 'authed', user: USER })
  })

  it('a 401 is a real anon: the store clears so the guard redirects', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'unauthorized' }), { status: 401 })),
    )

    await expect(bootstrapSession()).resolves.toBe('anon')

    expect(useAuthStore.getState().status).toBe('anon')
  })

  it('a network failure stays unknown — a dead server never reads as signed-out', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))

    await expect(bootstrapSession()).resolves.toBe('unreachable')

    expect(useAuthStore.getState().status).toBe('unknown')
  })

  it('a check that never settles times out to unreachable — no infinite splash, no unhandled rejection', async () => {
    // A proxy that accepts /auth/me and never answers: the promise never resolves OR rejects.
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => new Promise<Response>(() => {})))

    await expect(bootstrapSession(50)).resolves.toBe('unreachable')

    expect(useAuthStore.getState().status).toBe('unknown') // → the splash's retry, never a bounce
  })
})
