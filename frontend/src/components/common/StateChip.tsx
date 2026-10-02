import { CheckCircle, Circle, CircleNotch, Warning, WarningOctagon } from '@phosphor-icons/react'

export type RunStateWord = 'queued' | 'running' | 'complete' | 'converged' | 'failed' | 'interrupted'

export default function StateChip({ state }: { state: RunStateWord }) {
  const base = 'inline-flex items-center gap-1.5 rounded-[4px] border border-ink-700 bg-ink-800 px-2 py-1 text-label'
  switch (state) {
    case 'queued':
      return (
        <span className={`${base} text-paper-mute`}>
          <Circle size={14} aria-hidden="true" /> Queued
        </span>
      )
    case 'running':
      return (
        <span className={`${base} text-accent`}>
          <CircleNotch size={14} className="animate-spin" aria-hidden="true" /> Deliberating
        </span>
      )
    case 'converged':
      return (
        <span className={`${base} text-good`}>
          <CheckCircle size={14} aria-hidden="true" /> Converged
        </span>
      )
    case 'complete':
      return (
        <span className={`${base} text-good`}>
          <CheckCircle size={14} aria-hidden="true" /> Complete
        </span>
      )
    case 'failed':
      return (
        <span className={`${base} text-critical`}>
          <WarningOctagon size={14} aria-hidden="true" /> Failed
        </span>
      )
    case 'interrupted':
      return (
        <span className={`${base} text-brass`}>
          <Warning size={14} aria-hidden="true" /> Interrupted
        </span>
      )
  }
}
