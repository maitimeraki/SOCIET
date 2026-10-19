import type { InputHTMLAttributes } from 'react'

// §6 Inputs — the field notebook. No box and no fill: the field sits on a single ruled baseline.
// That rule is the control's boundary, so it takes --ink-3 (4.54:1 on the sheet) — --ink-4 is
// decorative and never a control boundary (addendum §1). Focus turns the rule accent and raises the
// corner registration tick, which the control paints itself so it registers on the control's own
// corner whether or not a `Field` wraps it.
const BASE =
  'corner-tick h-9 w-full border-b border-ink-3 bg-transparent px-0.5 text-body text-ink placeholder:text-ink-3 focus:border-accent aria-[invalid=true]:border-danger'

export default function Input({
  className = '',
  prefix,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { prefix?: string }) {
  const field = <input {...rest} className={`${BASE} ${className}`} />
  // The mono coordinate prefix is opt-in: without it the component renders the bare input it always
  // has, so every existing caller keeps the same DOM.
  if (!prefix) return field
  return (
    <span className="flex items-baseline gap-2">
      <span className="font-measurement text-mono text-ink-3">{prefix}</span>
      {field}
    </span>
  )
}
