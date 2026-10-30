import type { TextareaHTMLAttributes } from 'react'

// The one field baseline — `Input`'s ruled treatment (`border-b border-ink-3 bg-transparent`): no
// box, no fill, and no radius to round, because a ruled baseline has no corners. The padding is
// this control's own: a multi-line area is not the single-line field.

export default function Textarea({ className = '', ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...rest}
      className={`corner-tick w-full resize-none border-b border-ink-3 bg-transparent p-3 text-body text-ink placeholder:text-ink-2 focus:border-accent ${className}`}
    />
  )
}
