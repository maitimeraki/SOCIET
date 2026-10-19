import { CheckCircle, XCircle } from '@phosphor-icons/react'

export default function CommitLine({
  round,
  opinions,
  edges,
  failed,
}: {
  round: number
  opinions: number
  edges: number
  failed: boolean
}) {
  if (failed) {
    return (
      <p className="flex items-center gap-2 text-micro text-ink-2">
        <XCircle size={14} className="text-edge" aria-hidden="true" /> Pass {round}: commit failed
      </p>
    )
  }
  return (
    <p className="flex items-center gap-2 text-micro text-ink-3">
      <CheckCircle size={14} className="text-ink-2" aria-hidden="true" />
      Pass {round} committed — {opinions} opinions, {edges} connections
    </p>
  )
}
