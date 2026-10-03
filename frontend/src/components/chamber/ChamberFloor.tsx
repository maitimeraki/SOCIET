import { useMemo, useState } from 'react'
import { X } from '@phosphor-icons/react'
import type { AgentProfile, Stance } from '../../run/events'
import type { RunRound } from '../../run/reducer'
import { FLOOR_VIEWBOX, RADIUS_FRONT, SECTORS, arcSlots, pointAt } from './geometry'
import Seat from './Seat'
import type { SeatSpec } from './Seat'
import PairArc from './PairArc'
import StanceChip from '../common/StanceChip'

const SLOTS_PER_SECTOR = 12

export interface ChamberFloorProps {
  roster: AgentProfile[]
  rounds: RunRound[]
  /** null = live (latest round drawn); a number = replaying that round. */
  activeRound: number | null
  livePairs: Record<string, { a: string; b: string }>
  /** Profile navigation (floor tab); the control is hidden when omitted (roster seating mode). */
  onOpenProfile?: () => void
  compact?: boolean
}

export default function ChamberFloor({ roster, rounds, activeRound, livePairs, onOpenProfile }: ChamberFloorProps) {
  const [selected, setSelected] = useState<string | null>(null)

  const { seats, seatPositions } = useMemo(() => {
    const byStance: Record<Stance, AgentProfile[]> = { POSITIVE: [], NEUTRAL: [], AMBIVALENT: [], NEGATIVE: [] }
    for (const profile of roster) byStance[profile.stance as Stance].push(profile)

    const drawn = activeRound === null ? rounds[rounds.length - 1] : rounds.find((round) => round.round === activeRound)
    const spokeThisRound = new Set(drawn?.turns.map((turn) => turn.agent_name) ?? [])
    const everSpoke = new Set(rounds.flatMap((round) => round.turns.map((turn) => turn.agent_name)))

    const seats: SeatSpec[] = []
    const seatPositions = new Map<string, { x: number; y: number }>()
    for (const sector of SECTORS) {
      const members = byStance[sector.stance]
      const slots = arcSlots(sector.from, sector.to, Math.max(SLOTS_PER_SECTOR, members.length))
      members.forEach((profile, index) => {
        const slot = slots[index]
        const name = profile.identity.name
        seatPositions.set(name, slot)
        seats.push({
          profile,
          x: slot.x,
          y: slot.y,
          voice: spokeThisRound.has(name) ? 'spoke' : everSpoke.has(name) ? 'silent' : 'hollow',
          pulsing: Object.values(livePairs).some((pair) => pair.a === name || pair.b === name),
          onSelect: () => setSelected(name),
        })
      })
    }
    return { seats, seatPositions }
  }, [roster, rounds, activeRound, livePairs])

  // Arcs: this round at full strength, the previous round faded (§8.2 recency).
  const arcs = useMemo(() => {
    const drawn = activeRound === null ? rounds[rounds.length - 1] : rounds.find((round) => round.round === activeRound)
    const previous = activeRound === null ? rounds[rounds.length - 2] : rounds.find((round) => round.round === (activeRound ?? 0) - 1)
    const build = (round: RunRound | undefined, opacity: number) =>
      (round?.pairs ?? []).flatMap((pair) => {
        const a = seatPositions.get(pair.agent_a)
        const b = seatPositions.get(pair.agent_b)
        if (!a || !b) return []
        const active = Object.values(livePairs).some(
          (live) => (live.a === pair.agent_a && live.b === pair.agent_b) || (live.a === pair.agent_b && live.b === pair.agent_a),
        )
        return [{ a, b, active, opacity: active ? 1 : opacity }]
      })
    return [...build(previous, 0.45), ...build(drawn, 1)]
  }, [rounds, activeRound, livePairs, seatPositions])

  const seated = seats.find((seat) => seat.profile.identity.name === selected)

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${FLOOR_VIEWBOX.width} ${FLOOR_VIEWBOX.height}`}
        className="hidden w-full sm:block"
        role="group"
        aria-label="Chamber floor"
      >
        {SECTORS.flatMap((sector) =>
          arcSlots(sector.from, sector.to, SLOTS_PER_SECTOR).map((slot, index) => (
            <rect
              key={`etch-${sector.stance}-${index}`}
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
          const caption = pointAt((sector.from + sector.to) / 2, RADIUS_FRONT - 72)
          return (
            <text
              key={`caption-${sector.stance}`}
              x={caption.x}
              y={caption.y}
              textAnchor="middle"
              className="fill-[color:var(--color-paper-faint)] text-[11px] uppercase tracking-[0.08em]"
            >
              {sector.label}
            </text>
          )
        })}
        {arcs.map((arc, index) => (
          <PairArc key={index} arc={arc} />
        ))}
        {seats.map((seat) => (
          <Seat
            key={seat.profile.agent_id}
            seat={seat}
            tabIndex={0}
            onKeyNav={(delta) => {
              const list = seats.map((entry) => entry.profile.identity.name)
              const index = list.indexOf(seat.profile.identity.name)
              const next = list[(index + delta + list.length) % list.length]
              setSelected(null)
              document.querySelector<SVGGElement>(`[aria-label^="${next.replace(/"/g, '')}"]`)?.focus()
            }}
          />
        ))}
      </svg>

      {seated && (
        <div className="absolute right-3 top-3 w-[240px] rounded-[6px] border border-ink-600 bg-ink-800 p-3">
          <div className="flex items-start justify-between gap-2">
            <p className="text-body text-paper">{seated.profile.identity.name}</p>
            <button type="button" aria-label="Close popover" onClick={() => setSelected(null)} className="text-paper-mute hover:text-paper">
              <X size={12} aria-hidden="true" />
            </button>
          </div>
          <p className="text-micro text-paper-mute">{seated.profile.identity.archetype}</p>
          <div className="mt-2">
            <StanceChip stance={seated.profile.stance} size="sm" />
          </div>
          <p className="tnum mt-2 font-mono text-micro text-paper-dim">conf {seated.profile.confidence.toFixed(2)}</p>
          {onOpenProfile && (
            <button type="button" onClick={onOpenProfile} className="mt-2 inline-block text-micro text-accent hover:text-accent-strong">
              Open profile →
            </button>
          )}
        </div>
      )}

      {/* <640px: the floor degrades to the seats list (§17) */}
      <ul className="space-y-1 sm:hidden">
        {roster.map((profile) => (
          <li key={profile.agent_id} className="flex items-center gap-2 text-body text-paper-dim">
            <StanceChip stance={profile.stance} size="sm" />
            {profile.identity.name}
          </li>
        ))}
      </ul>
    </div>
  )
}
