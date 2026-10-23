import type { ReactNode } from 'react'
import { CheckCircle, Circle, CircleNotch, Warning, WarningOctagon } from '@phosphor-icons/react'

/**
 * §14.1 — a small bordered tag. One chip, three tones: `neutral` is the quiet tag, `status` is
 * the state chip, and `accent` is the one chip that means something is live.
 *
 * The 4px radius is the `--radius-xs` token, so the chip owns the only 4px radius in the kit.
 */
export type ChipTone = 'neutral' | 'status' | 'accent'

const TONE: Record<ChipTone, string> = {
  neutral: 'border-ink-3 bg-ground-2 text-ink-2',
  status: 'border-ink-3 bg-ground-2 text-ink',
  accent: 'border-accent bg-accent-soft text-accent',
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
    <span className={`inline-flex items-center gap-1.5 rounded-xs border px-2 py-1.5 text-label ${TONE[tone]} ${className}`}>
      {icon}
      {children}
    </span>
  )
}

/** The words a run's status can be read in. */
export type RunStateWord = 'queued' | 'running' | 'complete' | 'converged' | 'failed' | 'interrupted'

const STATE: Record<RunStateWord, { word: string; Icon: typeof Circle; live?: boolean }> = {
  queued: { word: 'Queued', Icon: Circle },
  running: { word: 'Deliberating', Icon: CircleNotch, live: true },
  converged: { word: 'Converged', Icon: CheckCircle },
  complete: { word: 'Complete', Icon: CheckCircle },
  failed: { word: 'Failed', Icon: WarningOctagon },
  interrupted: { word: 'Interrupted', Icon: Warning },
}

/**
 * The run's own state, as a chip: the state's own word, its own mark, and the accent while it
 * is live. The chip is the one component; this is the mapping from a run's status to it.
 */
export function StateChip({ state }: { state: RunStateWord }) {
  const { word, Icon, live } = STATE[state]
  return (
    <Chip
      tone={live ? 'accent' : 'status'}
      icon={<Icon size={14} className={live ? 'animate-spin' : undefined} aria-hidden="true" />}
    >
      {word}
    </Chip>
  )
}
