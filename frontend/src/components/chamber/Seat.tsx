import { motion, useReducedMotion } from 'framer-motion'
import type { AgentProfile, Stance } from '../../run/events'

export const SEAT_W = 14
export const SEAT_H = 10

const STANCE_VAR: Record<Stance, string> = {
  POSITIVE: 'var(--color-stance-pos)',
  NEUTRAL: 'var(--color-stance-neu)',
  AMBIVALENT: 'var(--color-stance-amb)',
  NEGATIVE: 'var(--color-stance-neg)',
}

export interface SeatSpec {
  profile: AgentProfile
  x: number
  y: number
  /** spoke this round | silent this round (spoke before) | never spoken */
  voice: 'spoke' | 'silent' | 'hollow'
  /** A pair_turn for this seat just landed — ring pulse. */
  pulsing: boolean
  onSelect: () => void
}

export default function Seat({ seat, tabIndex, onKeyNav }: { seat: SeatSpec; tabIndex: number; onKeyNav: (delta: number) => void }) {
  const reduced = useReducedMotion()
  const { profile, x, y } = seat
  const stance = profile.stance as Stance
  const fill = seat.voice === 'hollow' ? 'none' : STANCE_VAR[stance]
  const opacity = seat.voice === 'silent' ? 0.55 : 1

  return (
    <motion.g
      tabIndex={tabIndex}
      role="button"
      aria-label={`${profile.identity.name}, ${profile.identity.archetype}, ${stance}`}
      onKeyDown={(event) => {
        if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
          event.preventDefault()
          onKeyNav(1)
        }
        if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
          event.preventDefault()
          onKeyNav(-1)
        }
      }}
      onClick={seat.onSelect}
      initial={reduced ? false : { opacity: 0, y: 12 }}
      animate={{ opacity, y: 0 }}
      transition={{ duration: reduced ? 0 : 0.25, ease: [0.2, 0, 0, 1] }}
      className="cursor-pointer focus:outline-none"
    >
      <title>{`${profile.identity.name} · ${profile.identity.archetype} · ${stance} · conf ${profile.confidence.toFixed(2)}`}</title>
      <rect
        x={x - SEAT_W / 2}
        y={y - SEAT_H / 2}
        width={SEAT_W}
        height={SEAT_H}
        rx={3}
        fill={fill}
        stroke={seat.voice === 'spoke' ? 'var(--color-paper)' : STANCE_VAR[stance]}
        strokeWidth={seat.voice === 'spoke' ? 1 : 1.2}
      />
      {seat.pulsing && !reduced && (
        <>
          <motion.circle
            cx={x}
            cy={y}
            fill="none"
            stroke="var(--color-accent)"
            strokeWidth={1}
            initial={{ r: SEAT_W / 2 + 2, opacity: 0.8 }}
            animate={{ r: SEAT_W / 2 + 8, opacity: 0 }}
            transition={{ duration: 0.6, ease: [0.2, 0, 0, 1] }}
          />
          <motion.circle
            cx={x}
            cy={y}
            fill="none"
            stroke="var(--color-accent)"
            strokeWidth={1}
            initial={{ r: SEAT_W / 2 + 2, opacity: 0.8 }}
            animate={{ r: SEAT_W / 2 + 8, opacity: 0 }}
            transition={{ duration: 0.6, delay: 0.15, ease: [0.2, 0, 0, 1] }}
          />
        </>
      )}
      {seat.pulsing && reduced && <circle cx={x} cy={y} r={SEAT_W / 2 + 3} fill="none" stroke="var(--color-accent)" strokeWidth={1} />}
    </motion.g>
  )
}
