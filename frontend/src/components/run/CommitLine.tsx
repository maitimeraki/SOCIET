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
      <p className="flex items-center gap-2 text-micro text-route">
        <XCircle size={14} aria-hidden="true" /> Round {round}: commit failed
      </p>
    )
  }
  return (
    <p className="flex items-center gap-2 text-micro text-ink-3">
      <CheckCircle size={14} className="text-stance-pos" aria-hidden="true" />
      Round {round} committed — {opinions} opinions, {edges} edges
    </p>
  )
}
