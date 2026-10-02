import { CheckCircle } from '@phosphor-icons/react'

export default function StageLine({
  label,
  state,
  helper,
}: {
  label: string
  state: 'active' | 'done' | 'pending'
  helper?: string
}) {
  const glyph =
    state === 'done' ? (
      <CheckCircle size={16} className="text-good" aria-hidden="true" />
    ) : state === 'active' ? (
      <span aria-hidden="true" className="h-2.5 w-2.5 animate-pulse rounded-full bg-accent" />
    ) : (
      <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full border border-paper-faint" />
    )
  return (
    <div className="flex items-center gap-2.5">
      {glyph}
      <span className={`text-body ${state === 'pending' ? 'text-paper-mute' : 'text-paper'}`}>{label}</span>
      {helper && state === 'active' && <span className="text-micro text-paper-mute">{helper}</span>}
    </div>
  )
}
