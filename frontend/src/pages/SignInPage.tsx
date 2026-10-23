import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { SIGN_IN } from '../auth/authCopy'
import { CautionLine, IntakeStamp, PasswordField } from '../auth/authForm'
import {
  STAMP_MS,
  type AuthError,
  authErrorCopy,
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
 * §14.2 Sign-in — the intake form on the sheet. Fields sit on ruled baselines (`Field`/`Input`); the
 * submit is the route button ("Sign in"). Validation runs on blur and on submit; the invalid state
 * is the field's hatched margin note (never a red box), and the form-level error is the warn
 * caution line with its words in ink (R35). Success sets the store and routes to `next`.
 */
export default function SignInPage() {
  const signin = useAuthStore((s) => s.signin)
  const navigate = useNavigate()
  const [params] = useSearchParams()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [touched, setTouched] = useState({ email: false, password: false })
  const [submitted, setSubmitted] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<AuthError | null>(null)
  // Set once the session is adopted: the intake stamp holds, then the effect routes on. Keeping the
  // destination in state (not read from `params` in the effect) means the timer is never reset by a
  // re-render and the page cannot stall on the stamp.
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

  // The other door carries the same destination, so the round trip keeps where the visitor was
  // heading. `safeNext` runs on it first: only a same-origin path ever travels in the URL.
  const next = params.get('next')
  const nextSuffix = next ? `?next=${encodeURIComponent(safeNext(next))}` : ''

  async function submit() {
    if (submitting || redirectTo !== null) return
    setSubmitted(true)
    setError(null)
    if (emailError(email) || passwordError(password)) return
    setSubmitting(true)
    try {
      await signin(email, password) // sets the auth store on success
      setRedirectTo(safeNext(params.get('next')))
    } catch (err) {
      setError(authErrorCopy(err, 'signin'))
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
        <h1 className="font-titling text-title text-ink">{SIGN_IN.heading}</h1>
        <p className="mt-1 text-body text-ink-2">{SIGN_IN.lead}</p>
      </header>

      <Field label="Email" error={emailProblem ?? undefined}>
        <Input
          id="signin-email"
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
        id="signin-password"
        name="password"
        label="Password"
        error={passwordProblem ?? undefined}
        value={password}
        onChange={setPassword}
        onBlur={() => setTouched((t) => ({ ...t, password: true }))}
        autoComplete="current-password"
        disabled={submitting}
      />

      {error && <CautionLine error={error} onRetry={submit} />}

      {redirectTo !== null ? (
        <IntakeStamp label={SIGN_IN.stamp} />
      ) : (
        <Button type="submit" variant="primary" loading={submitting} className="max-lg:min-h-11">
          {SIGN_IN.action}
        </Button>
      )}

      <p className="text-body text-ink-3">
        {SIGN_IN.crossQuestion}{' '}
        <Link
          to={`/auth/signup${nextSuffix}`}
          className="inline-flex min-h-11 min-w-11 items-center font-titling text-body text-ink-2 underline decoration-ink-3 underline-offset-4 transition-colors duration-state hover:text-ink hover:decoration-accent lg:min-h-0 lg:min-w-0"
        >
          {SIGN_IN.crossAction}
        </Link>
      </p>
    </form>
  )
}
