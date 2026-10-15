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
      <span className="mb-1 block text-label uppercase text-ink-3">{label}</span>
      {children}
      {error ? (
        <span className="mt-1 block text-micro text-route">{error}</span>
      ) : hint ? (
        <span className="mt-1 block text-micro text-ink-3">{hint}</span>
      ) : null}
    </label>
  )
}
