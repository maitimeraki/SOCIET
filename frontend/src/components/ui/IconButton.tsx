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
      // §8.11 — a 44×44 control on the 8px corner: paper, one hairline. The tap target is the
      // control's own size, so no phone override is needed.
      className={`inline-flex h-11 w-11 items-center justify-center rounded-sm border border-hairline bg-paper text-ink-2 transition-colors duration-state hover:bg-sand hover:text-ink ${className}`}
    >
      {children}
    </button>
  )
}
