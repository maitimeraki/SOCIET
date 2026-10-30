import { cloneElement, isValidElement, useId, type ReactElement, type ReactNode } from 'react'
import Label from './Label'

export default function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string
  hint?: string
  error?: string
  children: ReactNode
}) {
  // The note (error or hint) is *described by* the control, not wrapped with it. A `<label>`'s text
  // content is the control's accessible name, so a note inside the label was absorbed into the name
  // and announced twice — once on focus, once by the live region (F4). The label now wraps only the
  // label text and the control; the note sits beside it and is referenced by id.
  const noteId = useId()
  const control = isValidElement(children)
    ? cloneElement(children as ReactElement<Record<string, unknown>>, {
        ...(error || hint ? { 'aria-describedby': noteId } : {}),
        ...(error ? { 'aria-errormessage': noteId, 'aria-invalid': true } : {}),
      })
    : children
  return (
    // The left margin is reserved unconditionally, so the 3px danger hatch (§8.2) marks the entry
    // without moving it. The hatch belongs to this row; the control owns its own box.
    <div className={`relative block pl-2.5 ${error ? 'field-invalid' : ''}`}>
      <label className="block">
        <Label className="mb-1 block">{label}</Label>
        {control}
      </label>
      {error ? (
        <span id={noteId} role="alert" className="mt-1 block text-micro text-danger">
          {error}
        </span>
      ) : hint ? (
        <span id={noteId} className="mt-1 block text-micro text-ink-3">
          {hint}
        </span>
      ) : null}
    </div>
  )
}
