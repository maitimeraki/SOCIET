import { motion, useReducedMotion } from 'framer-motion'
import { FLOOR_VIEWBOX, RADIUS_BACK, RADIUS_FRONT, SECTORS, arcPath, arcSlots, pointAt } from './geometry'

const ETCHED_PER_SECTOR = 8

export default function IdleFloor() {
  const reduced = useReducedMotion()
  return (
    <motion.svg
      viewBox={`0 0 ${FLOOR_VIEWBOX.width} ${FLOOR_VIEWBOX.height}`}
      className="w-full rounded-[12px] border border-ink-700 bg-ink-900"
      role="img"
      aria-label="The chamber floor, waiting for a society"
      initial="idle"
      whileHover="trace"
    >
      <text
        x={FLOOR_VIEWBOX.width / 2}
        y={36}
        textAnchor="middle"
        className="fill-[color:var(--color-paper-faint)] text-[13px] uppercase tracking-[0.3em]"
      >
        The Chamber Floor
      </text>

      {SECTORS.map((sector) =>
        arcSlots(sector.from, sector.to, ETCHED_PER_SECTOR).map((slot, i) => (
          <rect
            key={`${sector.stance}-${i}`}
            x={slot.x - 7}
            y={slot.y - 5}
            width={14}
            height={10}
            rx={3}
            fill="none"
            stroke="var(--color-ink-700)"
          />
        )),
      )}

      {SECTORS.map((sector) => {
        const mid = (sector.from + sector.to) / 2
        const p = pointAt(mid, RADIUS_FRONT - 72)
        return (
          <text
            key={`caption-${sector.stance}`}
            x={p.x}
            y={p.y}
            textAnchor="middle"
            className="fill-[color:var(--color-paper-faint)] text-[11px] uppercase tracking-[0.08em]"
          >
            {sector.label}
          </text>
        )
      })}

      {[RADIUS_FRONT, RADIUS_BACK].map((radius) => (
        <motion.path
          key={radius}
          d={arcPath(180, 360, radius)}
          fill="none"
          stroke="var(--color-accent)"
          strokeWidth={1.5}
          variants={reduced ? { idle: { opacity: 0 }, trace: { opacity: 0.4 } } : { idle: { pathLength: 0, opacity: 0 }, trace: { pathLength: 1, opacity: 0.5 } }}
          transition={{ duration: 0.6, ease: [0.2, 0, 0, 1] }}
        />
      ))}
    </motion.svg>
  )
}
