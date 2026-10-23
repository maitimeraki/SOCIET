import type { InputHTMLAttributes } from 'react'

// The one field baseline — `Input`'s ruled treatment (`border-b border-ink-3 bg-transparent`): no
// box, no fill, and no radius to round, because a ruled baseline has no corners. The padding is
// this control's own: a compact number field is not the text field.

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
      className="corner-tick tnum h-9 w-24 border-b border-ink-3 bg-transparent px-2 text-mono text-ink focus:border-accent"
    />
  )
}
