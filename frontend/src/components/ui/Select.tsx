import type { SelectHTMLAttributes } from 'react'

// The one field baseline — `Input`'s ruled treatment (`border-b border-ink-3 bg-transparent`): no
// box, no fill, and no radius to round, because a ruled baseline has no corners.

export default function Select({ className = '', children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...rest}
      className={`corner-tick h-9 border-b border-ink-3 bg-transparent px-2 text-body text-ink focus:border-accent ${className}`}
    >
      {children}
    </select>
  )
}
