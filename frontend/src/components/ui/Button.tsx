import type { ButtonHTMLAttributes } from 'react'
import { CircleNotch } from '@phosphor-icons/react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'text'
export type ButtonSize = 32 | 40 | 48

/**
 * §8.1 Buttons. One accent-filled control on a surface; the rest are paper, ink or a rule.
 * The primary is a FLAT evergreen fill — no ramp, no glow, no shadow, no fully rounded pill.
 * Every control shares one 6px radius and a 500 weight. The 32, 40 and 48px heights and the radius
 * match the controls measured on the reference sites.
 */
const VARIANT: Record<ButtonVariant, string> = {
  // primary — the action. The only accent-filled control on a surface; hover darkens the fill.
  primary: 'action-fill hover:bg-accent-hover',
  // secondary — paper, one record rule, an ink label.
  secondary: 'border border-rule bg-paper text-ink hover:bg-sand',
  // ghost — the underlined measurement link: mono, ruled beneath, no box. The underline is the
  // variant's only affordance, so it takes the record rule (§4.7: meaningful UI boundaries ≥3:1);
  // the decorative hairline is never a control's sole boundary.
  ghost:
    'font-mono text-mono text-ink-2 underline underline-offset-4 decoration-rule hover:text-ink hover:decoration-accent',
  // text — a plain sans action with no box or rule, for the nav's secondary action.
  text: 'text-ink-2 hover:text-ink',
  // danger — paper, one danger rule, a danger label.
  danger: 'border border-rule bg-paper text-danger hover:bg-danger/10',
}

/**
 * §10.4 — a standalone text link is still a target: at least 44px tall, with its label centred.
 * Links inside a sentence opt out explicitly; they are read as prose, not as controls.
 */
export const inlineLinkClasses = 'inline-flex min-h-11 min-w-11 items-center'

// eslint-disable-next-line react-refresh/only-export-components -- buttonClasses is the shared Link-as-button styling API (marketing, the shell)
export function buttonClasses(variant: ButtonVariant = 'secondary', size: ButtonSize = 40, extra = ''): string {
  const h = size === 48 ? 'h-12 px-6 text-body' : size === 40 ? 'h-10 px-4 text-body-sm' : 'h-8 px-3 text-control-sm'
  return `inline-flex select-none items-center justify-center gap-2 rounded-xs font-medium transition-[color,background-color,border-color,box-shadow,transform] duration-state disabled:cursor-not-allowed disabled:opacity-45 ${VARIANT[variant]} ${h} max-sm:min-h-11 max-sm:min-w-11 ${extra}`
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
