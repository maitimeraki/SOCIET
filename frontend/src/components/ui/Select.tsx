import type { SelectHTMLAttributes } from 'react'

export default function Select({ className = '', children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...rest}
      className={`corner-tick h-9 rounded-[4px] border border-ink-3 bg-ground-2 px-2 text-body text-ink focus:border-accent ${className}`}
    >
      {children}
    </select>
  )
}
