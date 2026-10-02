import { useState } from 'react'
import type { ReactNode } from 'react'
import { CaretDown } from '@phosphor-icons/react'

export default function Disclosure({ summary, children, defaultOpen = false }: { summary: ReactNode; children: ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border-b border-ink-700">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 py-3 text-left text-heading text-paper"
      >
        <CaretDown size={16} className={`transition-transform ${open ? '' : '-rotate-90'}`} aria-hidden="true" />
        {summary}
      </button>
      {open && <div className="pb-4">{children}</div>}
    </div>
  )
}
