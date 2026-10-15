import type { InputHTMLAttributes } from 'react'

export default function Input({ className = '', ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...rest}
      className={`h-9 w-full rounded-[4px] border border-ink-4 bg-survey-paper-2 px-3 text-body text-ink placeholder:text-ink-3 focus:border-datum ${className}`}
    />
  )
}
