export default function NumberField({
  value,
  onChange,
  min,
  max,
  step = 1,
  disabled = false,
}: {
  value: number
  onChange: (value: number) => void
  min: number
  max: number
  step?: number
  disabled?: boolean
}) {
  const clamp = (n: number) => Math.min(max, Math.max(min, n))
  return (
    <input
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
      className="tnum h-9 w-24 rounded-[4px] border border-ink-3 bg-survey-paper-2 px-2 text-mono text-ink focus:border-datum"
    />
  )
}
