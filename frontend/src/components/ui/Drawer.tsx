import { useEffect, useRef } from 'react'
import type { ReactNode, RefObject } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

// eslint-disable-next-line react-refresh/only-export-components -- useModalA11y is shared by Drawer and Dialog
export function useModalA11y(panel: RefObject<HTMLElement | null>, open: boolean, onClose: () => void) {
  // Latest-ref: callers pass inline closures, so keying the effect on onClose would
  // re-run it every parent render and steal focus back to the panel.
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  })

  useEffect(() => {
    if (!open) return
    const node = panel.current
    const opener = document.activeElement as HTMLElement | null
    node?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCloseRef.current()
      if (event.key === 'Tab' && node) {
        const focusables = node.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])')
        if (focusables.length === 0) return
        const first = focusables[0]
        const last = focusables[focusables.length - 1]
        // The panel itself is a boundary: Shift+Tab right after open lands on it.
        if (event.shiftKey && (document.activeElement === first || document.activeElement === node)) {
          event.preventDefault()
          last.focus()
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      opener?.focus()
    }
  }, [open, panel])
}

export default function Drawer({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const panel = useRef<HTMLDivElement>(null)
  useModalA11y(panel, open, onClose)
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 bg-ink-1000/60"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          onClick={onClose}
        >
          <motion.section
            ref={panel}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            aria-label={title}
            onClick={(event) => event.stopPropagation()}
            initial={{ x: 32, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 32, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.2, 0, 0, 1] }}
            className="absolute right-0 top-0 h-full w-full max-w-[560px] overflow-y-auto border-l border-ink-600 bg-ink-900 p-6"
          >
            <h2 className="mb-4 font-serif text-title text-paper">{title}</h2>
            {children}
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
