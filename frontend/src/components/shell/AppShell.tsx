import { Suspense } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import AppErrorBoundary from '../AppErrorBoundary'
// Imported by path, not through the `../ui` barrel: the barrel also re-exports Dialog/Drawer, whose
// framer-motion import would otherwise ride into the eagerly-loaded shell and the initial chunk.
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
 * §7 The app shell — ground, a 240px rail, a fluid region. There is no top bar. As a layout route it
 * renders `<Outlet/>` instead of `children`, so the chrome stays mounted across navigation.
 *
 * The route-level boundary and the page-chunk Suspense both live INSIDE the shell, wrapping the
 * Outlet: a crash or a slow chunk swaps only the content area, never the rail. The boundary is keyed
 * on the path so navigating elsewhere via the shell clears a stale fallback without a reload. Both
 * sit inside `<main>` and outside nothing else the rail depends on — the rail is a sibling of the
 * keyed subtree, so a page swap cannot blink it away.
 */
export default function AppShell() {
  const { pathname } = useLocation()
  return (
    <div className="flex min-h-screen bg-ground text-ink">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[70] focus:rounded-sm focus:bg-canvas focus:px-3 focus:py-2 focus:text-body focus:text-ink"
      >
        Skip to content
      </a>
      <Rail />
      <main id="content" className="min-w-0 flex-1 px-6 pb-24 pt-8">
        <AppErrorBoundary key={pathname}>
          <Suspense fallback={<RouteFallback />}>
            <Outlet />
          </Suspense>
        </AppErrorBoundary>
      </main>
      <ToastHost />
    </div>
  )
}
