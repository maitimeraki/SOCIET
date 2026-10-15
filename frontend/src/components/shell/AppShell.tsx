import type { ReactNode } from 'react'
import Masthead from './Masthead'
// Imported by path, not through the `../ui` barrel: the barrel also re-exports Dialog/Drawer, whose
// framer-motion import would otherwise ride into the eagerly-loaded shell and the initial chunk.
import { ToastHost } from '../ui/Toast'

export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-survey-paper font-record text-body text-ink">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[70] focus:rounded-[4px] focus:bg-survey-paper-2 focus:px-3 focus:py-2 focus:text-body focus:text-ink"
      >
        Skip to content
      </a>
      <Masthead />
      <main id="content" className="mx-auto w-full max-w-[1200px] px-6 pb-24 pt-8">
        {children}
      </main>
      <ToastHost />
    </div>
  )
}
