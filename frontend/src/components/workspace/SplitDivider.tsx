/* eslint-disable react-refresh/only-export-components -- the ratio helpers are this file's tested surface */
import { useRef } from 'react'
import type { PointerEvent } from 'react'

export const MIN_RATIO = 0.3
export const MAX_RATIO = 0.7
/** §7.7 — the split opens at 40% map / 60% output. */
export const DEFAULT_RATIO = 0.4

export function clampRatio(value: number, min = MIN_RATIO, max = MAX_RATIO): number {
  return Math.min(max, Math.max(min, value))
}

export function ratioFromKey(key: string | null): number {
  if (!key) return DEFAULT_RATIO
  const value = Number(key)
  return Number.isFinite(value) ? clampRatio(value) : DEFAULT_RATIO
}

/** The divider's own width — the seam is one 1px column, so the handle's centre is half a pixel in. */
export const HANDLE_WIDTH = 1

/** The ratio under the pointer, measured from the handle's centre rather than its left edge. */
export function ratioFromPointer(clientX: number, left: number, width: number, handle = HANDLE_WIDTH): number {
  return clampRatio((clientX - left - handle / 2) / width)
}

/**
 * §10.3 The seam between the map and the output. It is one 1px grid column, drags with the pointer,
 * and answers the arrow keys, Home and End; a double-click puts the split back at its 40% default.
 * Pointer capture keeps the drag on the separator itself, so no document-level listeners are needed.
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
      aria-label="Resize the map and the work"
      aria-orientation="vertical"
      aria-valuenow={Math.round(ratio * 100)}
      aria-valuemin={Math.round(MIN_RATIO * 100)}
      aria-valuemax={Math.round(MAX_RATIO * 100)}
      tabIndex={0}
      onDoubleClick={() => onChange(DEFAULT_RATIO)}
      onKeyDown={(event) => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
        event.preventDefault()
        if (event.key === 'ArrowLeft') onChange(clampRatio(ratio - 0.02))
        if (event.key === 'ArrowRight') onChange(clampRatio(ratio + 0.02))
        if (event.key === 'Home') onChange(MIN_RATIO)
        if (event.key === 'End') onChange(MAX_RATIO)
      }}
      onPointerDown={(event) => {
        if (event.button !== 0) return
        dragging.current = true
        event.currentTarget.setPointerCapture(event.pointerId)
      }}
      onPointerMove={(event) => {
        if (!dragging.current) return
        const rect = event.currentTarget.parentElement?.getBoundingClientRect()
        if (!rect || rect.width === 0) return
        onChange(ratioFromPointer(event.clientX, rect.left, rect.width))
      }}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onLostPointerCapture={() => {
        dragging.current = false
      }}
      className="order-2 hidden cursor-col-resize touch-none select-none items-center justify-center bg-hairline lg:flex"
    >
      <span aria-hidden="true" className="h-11 w-px bg-rule" />
    </div>
  )
}
