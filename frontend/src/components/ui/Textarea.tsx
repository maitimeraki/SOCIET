import type { TextareaHTMLAttributes } from 'react'

export default function Textarea({ className = '', ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...rest}
      className={`w-full resize-none rounded-[4px] border border-ink-700 bg-ink-800 p-3 text-body-lg text-paper placeholder:text-paper-mute focus:border-accent ${className}`}
    />
  )
}
