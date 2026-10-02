import type { InputHTMLAttributes } from 'react'

export default function Input({ className = '', ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...rest}
      className={`h-9 w-full rounded-[4px] border border-ink-700 bg-ink-800 px-3 text-body text-paper placeholder:text-paper-mute focus:border-accent ${className}`}
    />
  )
}
