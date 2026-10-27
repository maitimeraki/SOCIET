import { Suspense } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import AppErrorBoundary from '../AppErrorBoundary'
// Imported by path, and there is no `../ui` barrel any more: Drawer's framer-motion import
// would otherwise ride into the eagerly-loaded shell and the initial chunk.
import Skeleton from '../ui/Skeleton'
import { ToastHost } from '../ui/Toast'
import Rail from './Rail'

/** The page-chunk loading state — the same pulse skeleton the pages use, so the swap is seamless. */
export function RouteFallback() {
  return (
    <div role="status" aria-live="polite" className="flex flex-col gap-3">
      <span className="sr-only">Loading…</span>
      <Skeleton className="h-7 w-52" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-3/4" />
    </div>
  )
}

/**
 * The error boundary's route key — the first two path segments. A tab or step change inside one run
 * (`/runs/A/roster` → `/runs/A/verdict`) keeps the same key, so the mounted page and its map survive;
 * another run (`/runs/A/…` → `/runs/B/…`) or another top-level section takes a new key, so a caught
 * error is cleared when the customer moves somewhere else. Pure, so the rule is unit-tested.
 */
// eslint-disable-next-line react-refresh/only-export-components -- the key rule is pure logic, tested beside the shell
export function boundaryKey(pathname: string): string {
  return pathname.split('/').filter(Boolean).slice(0, 2).join('/')
}

/**
 * §7 The app shell — ground, a 240px rail, a fluid region. There is no top bar. As a layout route it
 * renders `<Outlet/>` instead of `children`, so the chrome stays mounted across navigation.
 *
 * The route-level boundary and the page-chunk Suspense both live INSIDE the shell, wrapping the
 * Outlet: a crash or a slow chunk swaps only the content area, never the rail. The boundary is keyed
 * on `boundaryKey(pathname)`, so moving to another run or section clears a stale fallback without a
 * reload while a tab change stays inside the same mounted page. Both sit inside `<main>` and outside
 * nothing else the rail depends on — the rail is a sibling of the keyed subtree, so a page swap
 * cannot blink it away.
 */
export default function AppShell() {
  const { pathname } = useLocation()
  const key = boundaryKey(pathname)
  return (
    <div className="flex min-h-screen bg-ground text-ink">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[70] focus:inline-flex focus:min-h-11 focus:min-w-11 focus:items-center focus:rounded-sm focus:bg-canvas focus:px-3 focus:py-2 focus:text-body focus:text-ink"
      >
        Skip to content
      </a>
      <Rail />
      <main id="content" className="min-w-0 flex-1 bg-[image:var(--gradient-ground)] px-6 pb-24 pt-8">
        <AppErrorBoundary key={key}>
          <Suspense fallback={<RouteFallback />}>
            <Outlet />
          </Suspense>
        </AppErrorBoundary>
      </main>
      <ToastHost />
    </div>
  )
}
