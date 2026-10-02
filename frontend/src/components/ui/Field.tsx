import type { ReactNode } from 'react'

export default function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string
  hint?: string
  error?: string
  children: ReactNode
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-label uppercase text-paper-mute">{label}</span>
      {children}
      {error ? (
        <span className="mt-1 block text-micro text-critical">{error}</span>
      ) : hint ? (
        <span className="mt-1 block text-micro text-paper-mute">{hint}</span>
      ) : null}
    </label>
  )
}
