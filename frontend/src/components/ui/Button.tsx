import type { ButtonHTMLAttributes } from 'react'
import { CircleNotch } from '@phosphor-icons/react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 32 | 40 | 48

/**
 * §8.1 Buttons. One accent-filled control on a surface; the rest are paper, ink or a rule.
 * The primary is a FLAT evergreen fill — no ramp, no glow, no fully rounded pill.
 * A 32px radius reads as a consumer app; this product is an instrument.
 */
const VARIANT: Record<ButtonVariant, string> = {
  // primary — the action. The only accent-filled control in the app.
  primary: 'action-fill rounded-md shadow-card hover:shadow-sheet',
  // secondary — paper, one record rule, an ink label.
  secondary: 'border border-rule bg-paper text-ink hover:bg-sand',
  // ghost — the underlined measurement link: mono, ruled beneath, no box.
  ghost:
    'font-mono text-mono text-ink-2 underline underline-offset-4 decoration-hairline hover:text-ink hover:decoration-accent',
  // danger — paper, one danger rule, a danger label.
  danger: 'border border-rule bg-paper text-danger hover:bg-danger/10',
}

// eslint-disable-next-line react-refresh/only-export-components -- buttonClasses is the shared Link-as-button styling API (marketing, the shell)
export function buttonClasses(variant: ButtonVariant = 'secondary', size: ButtonSize = 40, extra = ''): string {
  const h = size === 48 ? 'h-12 px-6 text-body' : size === 40 ? 'h-10 px-4 text-body-sm' : 'h-8 px-3 text-micro'
  return `inline-flex select-none items-center justify-center gap-2 rounded-md font-semibold transition-[color,background-color,border-color,box-shadow,transform] duration-state disabled:cursor-not-allowed disabled:opacity-45 ${VARIANT[variant]} ${h} max-sm:min-h-11 max-sm:min-w-11 ${extra}`
}

export default function Button({
  variant = 'secondary',
  size = 40,
  loading = false,
  disabled,
  className = '',
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: ButtonSize; loading?: boolean }) {
  return (
    <button {...rest} disabled={disabled || loading} className={buttonClasses(variant, size, className)}>
      {loading && <CircleNotch size={16} className="animate-spin" aria-hidden="true" />}
      {children}
    </button>
  )
}
