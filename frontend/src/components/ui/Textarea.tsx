import type { TextareaHTMLAttributes } from 'react'

// §8.2 — as `Input`, with the multi-line body: `resize-none`, 15px/23px copy, and the same
// paper field on the record rule. §7.7's question field is the one large variant: Fraunces 28px.

export default function Textarea({
  className = '',
  large = false,
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { large?: boolean }) {
  const size = large ? 'min-h-[132px] p-5 font-display text-[28px] leading-[36px]' : 'p-4 text-[15px] leading-[23px]'
  return (
    <textarea
      {...rest}
      className={`w-full resize-none rounded-sm border border-rule bg-paper text-ink placeholder:text-ink-3 focus:border-accent ${size} ${className}`}
    />
  )
}
