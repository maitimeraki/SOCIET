import type { ButtonHTMLAttributes } from 'react'
import { CircleNotch } from '@phosphor-icons/react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 32 | 40

// §6 Buttons — stamps and routes. Rectangular and square-cornered (no pills), hairline boundaries,
// and a corner registration mark at one corner. Colour is a mark and never a label: primary's route
// rule and danger's route outline are boundaries, so every label stays in ink (addendum §2).
const VARIANT: Record<ButtonVariant, string> = {
  // primary — the route button: the label rides a vermilion rule along the foot of an ink rectangle.
  primary: 'border border-ink-3 border-b-2 border-b-route text-ink hover:bg-route/10',
  // secondary — the ink outline. --ink-3 measures 4.54:1 on the sheet, clearing SC 1.4.11 (addendum §1).
  secondary: 'border border-ink-3 text-ink hover:border-ink hover:bg-survey-paper-2',
  // tertiary — the underlined measurement link: mono, ruled beneath, no box and so no registration mark.
  ghost:
    'font-measurement text-mono text-ink-2 underline underline-offset-4 decoration-ink-4 hover:text-ink hover:decoration-datum',
  // danger — the warning stamp: a route rule, ink label.
  danger: 'border border-route text-ink hover:bg-route/10',
}

// §6 The registration mark: a small hairline corner tick, one corner, present on the stamped variants.
const REGISTRATION =
  "relative after:pointer-events-none after:absolute after:right-0 after:top-0 after:h-1.5 after:w-1.5 after:border-r after:border-t after:border-ink-3 after:content-['']"

// eslint-disable-next-line react-refresh/only-export-components -- buttonClasses is the shared Link-as-button styling API (HomePage, ui barrel)
export function buttonClasses(variant: ButtonVariant = 'secondary', size: ButtonSize = 40, extra = ''): string {
  const h = size === 40 ? 'h-10 px-4 text-body' : 'h-8 px-3 text-micro'
  const mark = variant === 'ghost' ? '' : REGISTRATION
  return `inline-flex select-none items-center justify-center gap-2 ${mark} font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT[variant]} ${h} ${extra}`
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
