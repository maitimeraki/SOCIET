import Textarea from '../ui/Textarea'

export default function QueryComposer({
  id,
  value,
  onChange,
  onSubmit,
}: {
  /** Lets the caller's visual caption be a real `<label htmlFor>` — a placeholder is not a label. */
  id?: string
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
}) {
  return (
    <Textarea
      id={id}
      rows={3}
      value={value}
      autoFocus
      placeholder="Should we expand into the European market in 2027?"
      onChange={(event) => onChange(event.target.value)}
      onKeyDown={(event) => {
        if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') onSubmit()
      }}
    />
  )
}
