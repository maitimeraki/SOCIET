import { useId, useState } from 'react'
import { Eye, EyeSlash } from '@phosphor-icons/react'
import Button from '../components/ui/Button'
import IconButton from '../components/ui/IconButton'
import Input from '../components/ui/Input'
import Label from '../components/ui/Label'
import type { AuthError } from './authRules'

/* ── the auth form's state marks ──────────────────────────────────────────────────────────────────
   The two §7.2 marks the forms render, and the password row. The surface's *rules* — the security
   boundary (`safeNext`), the validators, the error copy and the stamp timing — live in
   `authRules.ts`; a module that exports components alongside plain values is exactly what
   `react-refresh/only-export-components` refuses, and these files are the first real consumers of
   that split. */

/**
 * §7.2 / §8.2 error state — the **3px danger hatch** at the left margin, the words in ink. The hatch
 * marks the block; the message stays a `role="alert"` line, so the hue is never the only signal.
 */
export function CautionLine({ error, onRetry }: { error: AuthError; onRetry: () => void }) {
  return (
    <div role="alert" className="field-invalid pl-3">
      <p className="text-body text-ink-2">{error.message}</p>
      {error.retry && (
        <Button type="button" variant="ghost" size={32} className="mt-1" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}

/**
 * §7.2 success state — the **intake stamp**: a warn impression and an ink word (R35), landing with
 * the `fix` move (a reading is taken) before the page routes on. The mark is warn; the label is ink.
 */
export function IntakeStamp({ label }: { label: string }) {
  return (
    <p role="status" className="fix inline-flex items-center gap-2 border border-warn px-3 py-2">
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" focusable="false" className="shrink-0">
        <circle cx="8" cy="8" r="6.2" fill="none" stroke="var(--color-warn)" strokeWidth="1.4" />
        <circle cx="8" cy="8" r="2.2" fill="var(--color-warn)" />
      </svg>
      <span className="text-label uppercase text-ink">{label}</span>
    </p>
  )
}

/**
 * §14.2 — the password row, composed outside `Field`.
 *
 * `Field` wraps its control in a `<label>`, and a `<label>` activates the **first** labelable
 * descendant — so a `<button>` inside one is a second control in the label's activation set: the
 * label's text would fire the toggle, and the toggle's name would compete with the field's own. The
 * toggle therefore cannot live inside `Field`'s label, and `Field` is left exactly as it is for
 * every other field in the app.
 *
 * So this row is composed from the kit's own pieces: the label is bound with `htmlFor` (the same
 * name the wrapping label gave the control), the control and the toggle share a row so the
 * baseline — the input's own bottom rule — is undisturbed, the toggle's own bounds are the phone's
 * 44×44, and the note is the same `role="alert"` line in ink that `Field` renders.
 */
export function PasswordField({
  id,
  name,
  label,
  hint,
  error,
  value,
  onChange,
  onBlur,
  autoComplete,
  disabled = false,
}: {
  id: string
  name: string
  label: string
  hint?: string
  error?: string
  value: string
  onChange: (value: string) => void
  onBlur: () => void
  autoComplete?: string
  disabled?: boolean
}) {
  const [shown, setShown] = useState(false)
  const noteId = useId()
  return (
    <div className={`relative block pl-2.5 ${error ? 'field-invalid' : ''}`}>
      <label className="block" htmlFor={id}>
        <Label className="mb-1 block">{label}</Label>
      </label>
      <div className="flex items-end gap-2">
        <Input
          id={id}
          name={name}
          type={shown ? 'text' : 'password'}
          autoComplete={autoComplete}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
          disabled={disabled}
          aria-describedby={error || hint ? noteId : undefined}
          aria-errormessage={error ? noteId : undefined}
          aria-invalid={error ? true : undefined}
          className="min-w-0 flex-1"
        />
        <IconButton
          type="button"
          label={shown ? 'Hide password' : 'Show password'}
          onClick={() => setShown((s) => !s)}
          className="min-h-11 min-w-11 shrink-0 lg:min-h-0 lg:min-w-0"
        >
          {shown ? <EyeSlash size={18} /> : <Eye size={18} />}
        </IconButton>
      </div>
      {error ? (
        <span id={noteId} role="alert" className="mt-1 block text-micro text-ink-2">
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
