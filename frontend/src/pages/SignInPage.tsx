import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  CautionLine,
  IntakeStamp,
  STAMP_MS,
  type AuthError,
  authErrorCopy,
  emailError,
  passwordError,
  safeNext,
} from '../auth/authForm'
import { useAuthStore } from '../auth/authStore'
import Button from '../components/ui/Button'
import Field from '../components/ui/Field'
import Input from '../components/ui/Input'

/**
 * §7.2 Sign-in — the intake form on the sheet. Fields sit on ruled baselines (`Field`/`Input`); the
 * submit is the route button ("Open the office"). Validation runs on blur and on submit; the invalid
 * state is `Field`'s vermilion hatched margin note (never a red box), and the form-level error is the
 * brass caution line with its words in ink (R35). Success sets the store and routes to `next`.
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

  const emailProblem = touched.email || submitted ? emailError(email) : null
  const passwordProblem = touched.password || submitted ? passwordError(password) : null

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
        <h1 className="font-titling text-title text-ink">Sign in</h1>
        <p className="mt-1 text-body text-ink-2">Open the office and pick up where you left off.</p>
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
          aria-invalid={emailProblem ? true : undefined}
        />
      </Field>

      <Field label="Password" error={passwordProblem ?? undefined}>
        <Input
          id="signin-password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onBlur={() => setTouched((t) => ({ ...t, password: true }))}
          aria-invalid={passwordProblem ? true : undefined}
        />
      </Field>

      {error && <CautionLine error={error} onRetry={submit} />}

      {redirectTo !== null ? (
        <IntakeStamp label="Signed in" />
      ) : (
        <Button type="submit" variant="primary" loading={submitting}>
          Open the office
        </Button>
      )}
    </form>
  )
}
