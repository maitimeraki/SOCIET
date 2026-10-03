import { motion } from 'framer-motion'
import { CX, CY } from './geometry'

export interface ArcSpec {
  a: { x: number; y: number }
  b: { x: number; y: number }
  active: boolean
  opacity: number
  onHover?: () => void
}

function arcPath(a: { x: number; y: number }, b: { x: number; y: number }): string {
  const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
  // Bow toward the chamber centre so the arc reads as a speech path, not a chord.
  const control = { x: mid.x + (CX - mid.x) * 0.25, y: mid.y + (CY - mid.y) * 0.25 }
  return `M ${a.x} ${a.y} Q ${control.x} ${control.y} ${b.x} ${b.y}`
}

export default function PairArc({ arc }: { arc: ArcSpec }) {
  return (
    <motion.path
      d={arcPath(arc.a, arc.b)}
      fill="none"
      stroke={arc.active ? 'var(--color-accent)' : 'var(--color-ink-600)'}
      strokeWidth={arc.active ? 2 : 1.5}
      initial={{ opacity: 0 }}
      animate={{ opacity: arc.opacity }}
      transition={{ duration: 0.2, ease: [0.2, 0, 0, 1] }}
      onMouseEnter={arc.onHover}
    />
  )
}
