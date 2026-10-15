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
      {/* The control row owns the corner registration tick (§6) and the hatched margin note an
          invalid field earns (§7.2). Both are CSS affordances, so no prop changes. */}
      <span className={`corner-tick block ${error ? 'field-invalid' : ''}`}>{children}</span>
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
