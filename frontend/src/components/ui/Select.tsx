import type { SelectHTMLAttributes } from 'react'

export default function Select({ className = '', children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...rest}
      className={`h-9 rounded-[4px] border border-ink-700 bg-ink-800 px-2 text-body text-paper focus:border-accent ${className}`}
    >
      {children}
    </select>
  )
}
