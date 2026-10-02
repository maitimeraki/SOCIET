import { create } from 'zustand'
import { CheckCircle, WarningCircle, Info } from '@phosphor-icons/react'
import type { Icon } from '@phosphor-icons/react'

type ToastKind = 'success' | 'error' | 'neutral'
interface ToastItem { id: number; kind: ToastKind; message: string }

interface ToastStore {
  toasts: ToastItem[]
  push: (kind: ToastKind, message: string) => void
  dismiss: (id: number) => void
}

let nextId = 1

export const useToastStore = create<ToastStore>((set, get) => ({
  toasts: [],
  push: (kind, message) => {
    const id = nextId++
    set({ toasts: [...get().toasts.slice(-2), { id, kind, message }] }) // max 3 stacked
    window.setTimeout(() => get().dismiss(id), 5000)
  },
  dismiss: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
}))

export function toast(kind: ToastKind, message: string) {
  useToastStore.getState().push(kind, message)
}

const ICON: Record<ToastKind, Icon> = { success: CheckCircle, error: WarningCircle, neutral: Info }
const ICON_CLASS: Record<ToastKind, string> = { success: 'text-good', error: 'text-critical', neutral: 'text-paper-mute' }

export function ToastHost() {
  const toasts = useToastStore((s) => s.toasts)
  return (
    <div className="fixed bottom-6 right-6 z-[60] flex flex-col gap-2" aria-live="polite">
      {toasts.map((t) => {
        const IconCmp = ICON[t.kind]
        return (
          <div key={t.id} className="flex items-center gap-2 rounded-[6px] border border-ink-600 bg-ink-800 px-4 py-3 text-body text-paper">
            <IconCmp size={16} className={ICON_CLASS[t.kind]} aria-hidden="true" />
            {t.message}
          </div>
        )
      })}
    </div>
  )
}
