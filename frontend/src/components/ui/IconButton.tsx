import type { ButtonHTMLAttributes } from 'react'

export default function IconButton({
  label,
  className = '',
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      {...rest}
      aria-label={label}
      title={label}
      // §14.5 — below 640px every actionable control is at least a 44×44 target; the desktop mark
      // stays 32. `min-*` wins over the height/width it exceeds, so the caller's own class still rules.
      className={`inline-flex h-8 w-8 items-center justify-center rounded-[4px] text-ink-2 transition-colors hover:bg-ground-2 hover:text-ink max-sm:min-h-11 max-sm:min-w-11 ${className}`}
    >
      {children}
    </button>
  )
}
