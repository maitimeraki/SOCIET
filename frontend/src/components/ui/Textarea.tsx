import type { TextareaHTMLAttributes } from 'react'

export default function Textarea({ className = '', ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...rest}
      className={`w-full resize-none rounded-[4px] border border-ink-3 bg-survey-paper-2 p-3 text-body-lg text-ink placeholder:text-ink-3 focus:border-datum ${className}`}
    />
  )
}
