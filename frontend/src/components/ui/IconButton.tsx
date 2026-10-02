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
      className={`inline-flex h-8 w-8 items-center justify-center rounded-[4px] text-paper-dim transition-colors hover:bg-ink-800 hover:text-paper ${className}`}
    >
      {children}
    </button>
  )
}
