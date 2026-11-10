import type { InputHTMLAttributes } from 'react'

// §8.2 — as `Input` (48px, paper, record rule, 8px corner), set in the mono, tabular face: a
// number is a measurement and never competes with prose.

type NumberFieldProps = {
  value: number
  onChange: (value: number) => void
  min: number
  max: number
  step?: number
  disabled?: boolean
} & Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange' | 'min' | 'max' | 'step' | 'disabled'>

export default function NumberField({
  value,
  onChange,
  min,
  max,
  step = 1,
  disabled = false,
  ...rest
}: NumberFieldProps) {
  const clamp = (n: number) => Math.min(max, Math.max(min, n))
  return (
    <input
      // `...rest` carries the ARIA a `Field` injects (`aria-describedby`/`aria-errormessage`/
      // `aria-invalid`); without it those attributes were dropped and the hint described nothing (F5).
      {...rest}
      type="number"
      value={value}
      min={min}
      max={max}
      step={step}
      disabled={disabled}
      onChange={(event) => {
        const next = Number(event.target.value)
        if (!Number.isNaN(next)) onChange(clamp(next))
      }}
      className="tnum h-12 w-24 rounded-sm border border-rule bg-paper px-4 font-mono text-mono text-ink focus:border-accent"
    />
  )
}
