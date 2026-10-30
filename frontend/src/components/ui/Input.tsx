import type { InputHTMLAttributes } from 'react'

// §6 Inputs — the field notebook. No box and no fill: the field sits on a single ruled baseline.
// That rule is the control's boundary, so it takes --ink-3 (4.54:1 on the sheet) — --hairline is
// decorative and never a control boundary (addendum §1). Focus turns the rule accent and raises the
// corner registration tick, which the control paints itself so it registers on the control's own
// corner whether or not a `Field` wraps it.
//
// The invalid state is NOT a red rule: the field's left margin carries the danger hatch, and a
// coloured baseline on top of it would be the red box the craft floor refuses. So the baseline
// stays --ink-3 when the field is invalid, and `aria-invalid` still marks the control for a
// screen reader.
const BASE =
  'corner-tick h-9 w-full border-b border-ink-3 bg-transparent px-0.5 text-body text-ink placeholder:text-ink-3 focus:border-accent'

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
      <span className="font-mono text-mono text-ink-3">{prefix}</span>
      {field}
    </span>
  )
}
