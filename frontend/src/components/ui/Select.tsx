import type { SelectHTMLAttributes } from 'react'

export default function Select({ className = '', children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...rest}
      className={`h-9 rounded-[4px] border border-ink-4 bg-survey-paper-2 px-2 text-body text-ink focus:border-datum ${className}`}
    >
      {children}
    </select>
  )
}
