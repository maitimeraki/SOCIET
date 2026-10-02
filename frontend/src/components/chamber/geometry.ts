import type { Stance } from '../../run/events'

export const FLOOR_VIEWBOX = { width: 1200, height: 520 }
const CX = 600
const CY = 560
export const RADIUS_FRONT = 480
export const RADIUS_BACK = 560

/** Four stance sectors, canonical order left→right (§3.5, §8.1). */
export const SECTORS: { stance: Stance; label: string; from: number; to: number }[] = [
  { stance: 'POSITIVE', label: 'AYE', from: 180, to: 225 },
  { stance: 'NEUTRAL', label: 'CROSSBENCH', from: 225, to: 270 },
  { stance: 'AMBIVALENT', label: 'CROSSBENCH', from: 270, to: 315 },
  { stance: 'NEGATIVE', label: 'NOE', from: 315, to: 360 },
]

export function pointAt(angleDeg: number, radius: number): { x: number; y: number } {
  const rad = (angleDeg * Math.PI) / 180
  return { x: CX + radius * Math.cos(rad), y: CY + radius * Math.sin(rad) }
}

/** Uniform seat slots across an arc span, alternating front/back arcs. */
export function arcSlots(from: number, to: number, count: number): { x: number; y: number; angle: number }[] {
  const slots: { x: number; y: number; angle: number }[] = []
  for (let i = 0; i < count; i++) {
    const t = (i + 0.5) / count
    const angle = from + (to - from) * t
    const radius = i % 2 === 0 ? RADIUS_FRONT : RADIUS_BACK
    slots.push({ ...pointAt(angle, radius), angle })
  }
  return slots
}

export function arcPath(from: number, to: number, radius: number): string {
  const start = pointAt(from, radius)
  const end = pointAt(to, radius)
  return `M ${start.x} ${start.y} A ${radius} ${radius} 0 0 1 ${end.x} ${end.y}`
}
