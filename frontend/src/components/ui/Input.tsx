import type { InputHTMLAttributes } from 'react'

// §8.2 Inputs — a 48px paper field on a record rule, with an 8px corner. Focus turns the rule
// evergreen; the 2px accent ring at 2px offset is the base `:focus-visible` ring, so the control
// does not paint a second, competing one.
const BASE =
  'h-12 w-full rounded-sm border border-rule bg-paper px-4 text-body text-ink placeholder:text-ink-3 focus:border-accent'

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
