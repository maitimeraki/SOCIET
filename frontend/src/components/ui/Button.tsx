import type { ButtonHTMLAttributes } from 'react'
import { CircleNotch } from '@phosphor-icons/react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 32 | 40

const VARIANT: Record<ButtonVariant, string> = {
  primary: 'bg-datum text-survey-paper hover:bg-datum active:bg-datum',
  secondary: 'border border-ink-4 text-ink hover:border-datum hover:text-datum',
  ghost: 'text-ink-2 hover:bg-survey-paper-2 hover:text-ink',
  danger: 'border border-route text-route hover:bg-route/10',
}

// eslint-disable-next-line react-refresh/only-export-components -- buttonClasses is the shared Link-as-button styling API (HomePage, ui barrel)
export function buttonClasses(variant: ButtonVariant = 'secondary', size: ButtonSize = 40, extra = ''): string {
  const h = size === 40 ? 'h-10 px-4 text-body' : 'h-8 px-3 text-micro'
  return `inline-flex select-none items-center justify-center gap-2 rounded-[4px] font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT[variant]} ${h} ${extra}`
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
