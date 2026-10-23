import type { ButtonHTMLAttributes } from 'react'
import { CircleNotch } from '@phosphor-icons/react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 32 | 40

// §6 Buttons — the action, and the stamps. `primary` is the one accent-filled control on a
// surface: the §3 action ramp with the on-accent ink as its label. The ink stamp is the
// secondary: a hairline boundary, a foot rule and a corner registration mark. Colour is a mark
// and never a label — every label stays in ink, and only the accent fill carries a light one.
const VARIANT: Record<ButtonVariant, string> = {
  // primary — the action. The accent ramp (7.24:1 under the white label), radius-md, and a soft
  // shadow that seats it on the page. It is the only accent-filled control in the app.
  primary: 'action-fill rounded-md shadow-raised hover:shadow-floating',
  // secondary — the ink stamp: an ink-3 outline with a 2px border-strong foot and a corner
  // registration tick. --ink-3 measures 4.54:1 on the sheet, clearing SC 1.4.11 (addendum §1).
  secondary: 'border border-ink-3 text-ink hover:border-ink hover:bg-ground-2',
  // tertiary — the underlined measurement link: mono, ruled beneath, no box and so no registration
  // mark. The underline is the only cue separating it from body prose, so it is a control affordance
  // and takes --ink-3 (4.54:1) — --ink-4 is for separators and rules, never a control's affordance.
  ghost:
    'font-measurement text-mono text-ink-2 underline underline-offset-4 decoration-ink-3 hover:text-ink hover:decoration-accent',
  // danger — the warning stamp: a route rule, ink label.
  danger: 'border border-border-strong text-ink hover:bg-danger/10',
}

// §6 The registration mark: a small hairline corner tick, one corner, present on the stamped
// variants. The accent-filled action carries no mark — a tick on a filled surface is a second
// thing competing with the fill, and the fill is the whole signal.
const REGISTRATION =
  "relative after:pointer-events-none after:absolute after:right-0 after:top-0 after:h-1.5 after:w-1.5 after:border-r after:border-t after:border-ink-3 after:content-['']"

// eslint-disable-next-line react-refresh/only-export-components -- buttonClasses is the shared Link-as-button styling API (marketing, dashboardView)
export function buttonClasses(variant: ButtonVariant = 'secondary', size: ButtonSize = 40, extra = ''): string {
  const h = size === 40 ? 'h-10 px-4 text-body' : 'h-8 px-3 text-micro'
  const mark = variant === 'ghost' || variant === 'primary' ? '' : REGISTRATION
  // §14.5 — below 640px every actionable control is at least a 44×44 target; the desktop heights
  // (32 / 40) are unchanged. `min-*` wins over the height it exceeds.
  return `inline-flex select-none items-center justify-center gap-2 ${mark} rounded-md font-medium transition-[color,background-color,border-color,box-shadow,transform] duration-state disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT[variant]} ${h} max-sm:min-h-11 max-sm:min-w-11 ${extra}`
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
