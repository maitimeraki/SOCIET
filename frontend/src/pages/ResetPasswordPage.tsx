import { useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApiError, authResetConfirm } from '../api/rest'
import { PasswordField } from '../auth/authForm'
import { passwordError } from '../auth/authRules'
import Button, { inlineLinkClasses } from '../components/ui/Button'

const LINK = `${inlineLinkClasses} font-ui text-body text-accent underline underline-offset-4`

/** The confirm field's own rule; the password rule is the existing `passwordError` (MIN_PASSWORD). */
// eslint-disable-next-line react-refresh/only-export-components -- confirmError is the tested rule
export function confirmError(password: string, confirm: string): string | null {
  if (confirm === '') return 'Repeat your new password.'
  if (confirm !== password) return "The two passwords don't match."
  return null
}

/** The whole form's rule, derived from the current values so it clears as soon as they agree. */
// eslint-disable-next-line react-refresh/only-export-components -- resetProblem is the tested rule
export function resetProblem(password: string, confirm: string): string | null {
  return passwordError(password) ?? confirmError(password, confirm)
}

/**
 * Only 400/422 are the server saying the link or the password is dead. Anything else (5xx,
 * network) is retryable and must not send the customer down the "expired link" path.
 */
// eslint-disable-next-line react-refresh/only-export-components -- resetFailure is the tested mapping
export function resetFailure(error: unknown): { invalid: boolean; message: string } {
  if (error instanceof ApiError && (error.status === 400 || error.status === 422)) {
    return { invalid: true, message: error.detail }
  }
  if (error instanceof ApiError) return { invalid: false, message: error.detail }
  return {
    invalid: false,
    message: "Couldn't reach the server. Check your connection and try again.",
  }
}

export function ResetPasswordView({ state, message }: { state: 'success' | 'invalid'; message?: string }) {
  if (state === 'success') {
    return (
      <>
        <h1 className="font-display text-display font-medium tracking-[-0.03em] text-ink">
          Password changed
        </h1>
        <p className="mt-3 text-body text-ink-2">You can sign in with your new password.</p>
        <Link to="/auth/signin" className={`${LINK} mt-6`}>
          Sign in
        </Link>
      </>
    )
  }
  return (
    <>
      <h1 className="font-display text-display font-medium tracking-[-0.03em] text-ink">
        This link is invalid or has expired
      </h1>
      <p className="mt-3 text-body text-ink-2">
        {message ?? "Request a new link and we'll send another."}
      </p>
      <Link to="/auth/forgot" className={`${LINK} mt-6`}>
        Request a new link
      </Link>
    </>
  )
}

/** `/auth/reset?token=…` — choose a new password from the link the server minted. */
export default function ResetPasswordPage() {
  const [params] = useSearchParams()
  const token = params.get('token')
  const [phase, setPhase] = useState<'form' | 'success' | 'invalid'>(token ? 'form' : 'invalid')
  const [message, setMessage] = useState<string | undefined>()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [touched, setTouched] = useState({ password: false, confirm: false })
  const [submitted, setSubmitted] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (phase !== 'form') return <ResetPasswordView state={phase} message={message} />

  const passwordProblem = submitted || touched.password ? passwordError(password) : null
  const confirmationProblem = submitted || touched.confirm ? confirmError(password, confirm) : null

  async function submit() {
    if (!token || submitting) return
    setSubmitted(true)
    setError(null)
    if (resetProblem(password, confirm)) return
    setSubmitting(true)
    try {
      await authResetConfirm(token, password)
      setPhase('success')
    } catch (err) {
      const failure = resetFailure(err)
      if (failure.invalid) {
        setMessage(failure.message)
        setPhase('invalid')
        return
      }
      setError(failure.message)
      setSubmitting(false)
    }
  }

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    void submit()
  }

  return (
    <form onSubmit={onSubmit} noValidate aria-busy={submitting} className="space-y-6">
      <header>
        <h1 className="font-display text-display font-medium tracking-[-0.03em] text-ink">
          Choose a new password
        </h1>
      </header>

      <PasswordField
        id="reset-password"
        name="password"
        label="New password"
        error={passwordProblem ?? undefined}
        value={password}
        onChange={setPassword}
        onBlur={() => setTouched((t) => ({ ...t, password: true }))}
        autoComplete="new-password"
        disabled={submitting}
      />

      <PasswordField
        id="reset-confirm"
        name="confirm"
        label="Confirm new password"
        error={confirmationProblem ?? undefined}
        value={confirm}
        onChange={setConfirm}
        onBlur={() => setTouched((t) => ({ ...t, confirm: true }))}
        autoComplete="new-password"
        disabled={submitting}
      />

      {error && (
        <p role="alert" className="text-body text-ink-2">
          {error}
        </p>
      )}

      <Button type="submit" variant="primary" loading={submitting} className="max-lg:min-h-11">
        Change password
      </Button>

      <Link to="/auth/signin" className={`${LINK} min-h-11`}>
        Back to sign in
      </Link>
    </form>
  )
}
