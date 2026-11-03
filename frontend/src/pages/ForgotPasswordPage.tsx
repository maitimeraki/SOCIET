import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, authResetRequest } from '../api/rest'
import { emailError } from '../auth/authRules'
import Button, { inlineLinkClasses } from '../components/ui/Button'
import Field from '../components/ui/Field'
import Input from '../components/ui/Input'

const LINK = `${inlineLinkClasses} font-ui text-body text-ink-2 underline underline-offset-4`

/**
 * The one success state — identical whether or not the address has an account. The server answers
 * 202 either way; the page must not become an address oracle.
 */
export function ForgotPasswordSentView() {
  return (
    <>
      <h1 className="font-display text-display font-medium tracking-[-0.03em] text-ink">
        Check your email
      </h1>
      <p className="mt-3 text-body text-ink-2">
        If that address has an account, a reset link is on its way.
      </p>
      <Link to="/auth/signin" className={`${LINK} mt-6`}>
        Back to sign in
      </Link>
    </>
  )
}

/** `/auth/forgot` — ask for a reset link. The address is never confirmed to exist. */
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [sending, setSending] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    if (sending) return
    setError(null)
    const invalid = emailError(email)
    setProblem(invalid)
    if (invalid) return
    setSending(true)
    try {
      await authResetRequest(email.trim())
      setSent(true)
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.detail
          : "Couldn't reach the server. Check your connection and try again.",
      )
      setSending(false)
    }
  }

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    void submit()
  }

  if (sent) return <ForgotPasswordSentView />

  return (
    <form onSubmit={onSubmit} noValidate aria-busy={sending} className="space-y-6">
      <header>
        <h1 className="font-display text-display font-medium tracking-[-0.03em] text-ink">
          Reset your password
        </h1>
        <p className="mt-3 text-body text-ink-2">
          Enter the email you signed up with and we'll send a reset link.
        </p>
      </header>

      <Field label="Email" error={problem ?? undefined}>
        <Input
          id="forgot-email"
          name="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={sending}
          aria-invalid={problem ? true : undefined}
        />
      </Field>

      {error && (
        <p role="alert" className="text-body text-ink-2">
          {error}
        </p>
      )}

      <Button type="submit" variant="primary" loading={sending} className="max-lg:min-h-11">
        Send reset link
      </Button>

      <Link to="/auth/signin" className={LINK}>
        Back to sign in
      </Link>
    </form>
  )
}
