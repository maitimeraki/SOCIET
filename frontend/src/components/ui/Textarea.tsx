import type { TextareaHTMLAttributes } from 'react'

// §8.2 — as `Input`, with the multi-line body: `resize-none`, 15px/23px copy, and the same
// paper field on the record rule.

export default function Textarea({ className = '', ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...rest}
      className={`w-full resize-none rounded-sm border border-rule bg-paper p-4 text-[15px] leading-[23px] text-ink placeholder:text-ink-3 focus:border-accent ${className}`}
    />
  )
}
