import { useRef } from 'react'
import type { PointerEvent } from 'react'

export const MIN_RATIO = 0.25
export const MAX_RATIO = 0.75

export function clampRatio(value: number, min = MIN_RATIO, max = MAX_RATIO): number {
  return Math.min(max, Math.max(min, value))
}

export function ratioFromKey(key: string | null): number {
  if (!key) return 0.5
  const value = Number(key)
  return Number.isFinite(value) ? clampRatio(value) : 0.5
}

/**
 * §9 The seam between the map and the work. It is one grid column wide (8px), drags with the pointer,
 * and answers the arrow keys, Home and End; a double-click puts the split back at 50%. Pointer capture
 * keeps the drag on the separator itself, so no document-level listeners are needed.
 */
export default function SplitDivider({ ratio, onChange }: { ratio: number; onChange: (ratio: number) => void }) {
  const dragging = useRef(false)

  const endDrag = (event: PointerEvent<HTMLDivElement>) => {
    dragging.current = false
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
  }

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-valuenow={Math.round(ratio * 100)}
      aria-valuemin={25}
      aria-valuemax={75}
      tabIndex={0}
      onDoubleClick={() => onChange(0.5)}
      onKeyDown={(event) => {
        if (event.key === 'ArrowLeft') onChange(clampRatio(ratio - 0.02))
        if (event.key === 'ArrowRight') onChange(clampRatio(ratio + 0.02))
        if (event.key === 'Home') onChange(MIN_RATIO)
        if (event.key === 'End') onChange(MAX_RATIO)
      }}
      onPointerDown={(event) => {
        dragging.current = true
        event.currentTarget.setPointerCapture(event.pointerId)
      }}
      onPointerMove={(event) => {
        if (!dragging.current) return
        const rect = event.currentTarget.parentElement?.getBoundingClientRect()
        if (!rect || rect.width === 0) return
        onChange(clampRatio((event.clientX - rect.left) / rect.width))
      }}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      className="order-2 hidden cursor-col-resize touch-none select-none items-center justify-center border-x border-rule/50 bg-ground-2 lg:flex"
    >
      <span aria-hidden="true" className="text-ink-3">⋮</span>
    </div>
  )
}
