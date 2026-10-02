import type { ReactNode } from 'react'
import Masthead from './Masthead'
import { ToastHost } from '../ui'

export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-ink-1000 font-sans text-body text-paper">
      <Masthead />
      <main className="mx-auto w-full max-w-[1200px] px-6 pb-24 pt-8">{children}</main>
      <ToastHost />
    </div>
  )
}
