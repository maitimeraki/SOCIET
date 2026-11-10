import type { SelectHTMLAttributes } from 'react'

// §8.2 — as `Input`, wrapping the platform's own `<select>`.

export default function Select({ className = '', children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...rest}
      className={`h-12 rounded-sm border border-rule bg-paper px-4 text-body text-ink focus:border-accent ${className}`}
    >
      {children}
    </select>
  )
}
