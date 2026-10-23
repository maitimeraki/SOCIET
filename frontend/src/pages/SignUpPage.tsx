import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { SIGN_UP } from '../auth/authCopy'
import { CautionLine, IntakeStamp, PasswordField } from '../auth/authForm'
import {
  MIN_PASSWORD,
  STAMP_MS,
  type AuthError,
  authErrorCopy,
  confirmError,
  emailError,
  fieldProblem,
  passwordError,
  safeNext,
} from '../auth/authRules'
import { useAuthStore } from '../auth/authStore'
import Button from '../components/ui/Button'
import Field from '../components/ui/Field'
import Input from '../components/ui/Input'

/**
 * §14.2 Sign-up — the same intake form as sign-in plus the confirm field. It states its real cost
 * and nothing it cannot back: the form asks for an address and a password, so that is all the copy
 * claims — no plan, no price, no billing line (PRODUCT.md §4; pricing is undecided). The cost is
 * stated **once**, on this form only (D2).
 *
 * The invalid mark is the field's own hatch — a mark at the left edge, never a red box — and it is
 * re-derived from each field's current value, so it clears the moment that value becomes valid.
 */
export default function SignUpPage() {
  const signup = useAuthStore((s) => s.signup)
  const navigate = useNavigate()
  const [params] = useSearchParams()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [touched, setTouched] = useState({ email: false, password: false, confirm: false })
  const [submitted, setSubmitted] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<AuthError | null>(null)
  const [redirectTo, setRedirectTo] = useState<string | null>(null)

  useEffect(() => {
    if (redirectTo === null) return
    const id = setTimeout(() => navigate(redirectTo, { replace: true }), STAMP_MS)
    return () => clearTimeout(id)
  }, [redirectTo, navigate])

  // The mark is derived from the value, not stored: a paste or an autofill clears it as surely as
  // a keystroke, and a submit does not freeze the other fields red while one is corrected.
  const emailProblem = fieldProblem(email, touched.email, submitted, emailError)
  const passwordProblem = fieldProblem(password, touched.password, submitted, passwordError)
  const confirmProblem = fieldProblem(confirm, touched.confirm, submitted, (value) =>
    confirmError(password, value),
  )

  // The other door carries the same destination, so the round trip keeps where the visitor was
  // heading. `safeNext` runs on it first: only a same-origin path ever travels in the URL.
  const next = params.get('next')
  const nextSuffix = next ? `?next=${encodeURIComponent(safeNext(next))}` : ''

  async function submit() {
    if (submitting || redirectTo !== null) return
    setSubmitted(true)
    setError(null)
    if (emailError(email) || passwordError(password) || confirmError(password, confirm)) return
    setSubmitting(true)
    try {
      await signup(email, password) // sets the auth store on success
      setRedirectTo(safeNext(params.get('next')))
    } catch (err) {
      setError(authErrorCopy(err, 'signup'))
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
        <h1 className="font-titling text-title text-ink">{SIGN_UP.heading}</h1>
        <p className="mt-1 text-body text-ink-2">{SIGN_UP.lead}</p>
      </header>

      <Field label="Email" error={emailProblem ?? undefined}>
        <Input
          id="signup-email"
          name="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onBlur={() => setTouched((t) => ({ ...t, email: true }))}
          disabled={submitting}
          aria-invalid={emailProblem ? true : undefined}
        />
      </Field>

      <PasswordField
        id="signup-password"
        name="password"
        label="Password"
        hint={`At least ${MIN_PASSWORD} characters`}
        error={passwordProblem ?? undefined}
        value={password}
        onChange={setPassword}
        onBlur={() => setTouched((t) => ({ ...t, password: true }))}
        autoComplete="new-password"
        disabled={submitting}
      />

      <PasswordField
        id="signup-confirm"
        name="confirm"
        label="Confirm password"
        error={confirmProblem ?? undefined}
        value={confirm}
        onChange={setConfirm}
        onBlur={() => setTouched((t) => ({ ...t, confirm: true }))}
        autoComplete="new-password"
        disabled={submitting}
      />

      {error && <CautionLine error={error} onRetry={submit} />}

      {redirectTo !== null ? (
        <IntakeStamp label={SIGN_UP.stamp} />
      ) : (
        <Button type="submit" variant="primary" loading={submitting} className="max-lg:min-h-11">
          {SIGN_UP.action}
        </Button>
      )}

      <p className="text-pretty font-measurement text-mono text-ink-3">{SIGN_UP.cost}</p>

      <p className="text-body text-ink-3">
        {SIGN_UP.crossQuestion}{' '}
        <Link
          to={`/auth/signin${nextSuffix}`}
          className="inline-flex min-h-11 min-w-11 items-center font-titling text-body text-ink-2 underline decoration-ink-3 underline-offset-4 transition-colors duration-state hover:text-ink hover:decoration-accent lg:min-h-0 lg:min-w-0"
        >
          {SIGN_UP.crossAction}
        </Link>
      </p>
    </form>
  )
}
