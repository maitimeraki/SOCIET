import Textarea from '../ui/Textarea'

export default function QueryComposer({
  value,
  onChange,
  onSubmit,
}: {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
}) {
  return (
    <Textarea
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
