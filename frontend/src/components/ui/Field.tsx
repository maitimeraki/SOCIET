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
    // The left margin is reserved unconditionally, so the invalid hatch (§7.2) marks the entry
    // without moving it. The corner registration tick (§6) belongs to the control, not to this
    // row — a stretched row would register the mark against the grid cell, not the field.
    <label className={`relative block pl-2.5 ${error ? 'field-invalid' : ''}`}>
      <span className="mb-1 block text-label uppercase text-ink-3">{label}</span>
      {children}
      {error ? (
        <span role="alert" className="mt-1 block text-micro text-ink-2">
          {error}
        </span>
      ) : hint ? (
        <span className="mt-1 block text-micro text-ink-3">{hint}</span>
      ) : null}
    </label>
  )
}
