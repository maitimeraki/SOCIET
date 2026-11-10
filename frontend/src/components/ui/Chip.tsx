import type { ReactNode } from 'react'
import { CheckCircle, Circle, CircleNotch, Warning, WarningOctagon } from '@phosphor-icons/react'

/**
 * §8.4 — a chip is a 24px mono caps tag on the 6px corner. The tone is the only fill; the
 * geometry is shared. Status is always mark + word, never a bare dot.
 */
export type ChipTone = 'neutral' | 'verified' | 'caution' | 'danger'

const TONE: Record<ChipTone, string> = {
  // neutral — the quiet tag.
  neutral: 'bg-sand text-ink-2',
  // verified — a settled state: complete, converged, read.
  verified: 'bg-accent-soft text-ok',
  // caution — a state that is waiting or partial.
  caution: 'bg-sand text-warn',
  // danger — a failure: paper, one record rule, a danger word.
  danger: 'border border-rule bg-paper text-danger',
}

export default function Chip({
  children,
  tone = 'neutral',
  icon,
  className = '',
}: {
  children: ReactNode
  tone?: ChipTone
  icon?: ReactNode
  className?: string
}) {
  return (
    <span
      className={`inline-flex h-6 items-center gap-1.5 rounded-xs px-2 font-mono text-[10px] leading-4 uppercase tracking-[0.04em] ${TONE[tone]} ${className}`}
    >
      {icon}
      {children}
    </span>
  )
}

/** The words a run's status can be read in. */
export type RunStateWord =
  | 'queued'
  | 'running'
  | 'complete'
  | 'completed'
  | 'converged'
  | 'failed'
  | 'interrupted'
  | 'cancelled'

interface StateEntry {
  word: string
  Icon: typeof Circle
  tone: ChipTone
  live?: boolean
}

const STATE: Record<RunStateWord, StateEntry> = {
  queued: { word: 'Queued', Icon: Circle, tone: 'neutral' },
  running: { word: 'Deliberating', Icon: CircleNotch, tone: 'caution', live: true },
  converged: { word: 'Converged', Icon: CheckCircle, tone: 'verified' },
  complete: { word: 'Complete', Icon: CheckCircle, tone: 'verified' },
  // `completed` is the extraction jobs' spelling; a run summary may carry either.
  completed: { word: 'Complete', Icon: CheckCircle, tone: 'verified' },
  failed: { word: 'Failed', Icon: WarningOctagon, tone: 'danger' },
  interrupted: { word: 'Interrupted', Icon: Warning, tone: 'caution' },
  // A cancelled run ended early; it is neither a failure nor still working.
  cancelled: { word: 'Cancelled', Icon: Circle, tone: 'neutral' },
}

/** Any status this map has not met still renders a mark and an honest word, never a crash. */
const UNKNOWN: StateEntry = { word: 'Unknown', Icon: Circle, tone: 'neutral' }

/**
 * The run's own state, as a chip: the state's own word, its own mark, and the mark turning while
 * the run is live. The chip is the one component; this is the mapping from a run's status to it.
 * The prop is a plain string because the backend is the source of the status — a value outside the
 * union reads as Unknown rather than throwing.
 */
export function StateChip({ state }: { state: string }) {
  const { word, Icon, tone, live } = (STATE as Record<string, StateEntry | undefined>)[state] ?? UNKNOWN
  return (
    <Chip tone={tone} icon={<Icon size={14} className={live ? 'animate-spin' : undefined} aria-hidden="true" />}>
      {word}
    </Chip>
  )
}
