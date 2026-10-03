import type { ReactNode } from 'react'
import Masthead from './Masthead'
import { ToastHost } from '../ui'

export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-ink-1000 font-sans text-body text-paper">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[70] focus:rounded-[4px] focus:bg-ink-800 focus:px-3 focus:py-2 focus:text-body focus:text-paper"
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
