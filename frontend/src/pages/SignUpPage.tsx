import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { CautionLine, IntakeStamp } from '../auth/authForm'
import {
  MIN_PASSWORD,
  STAMP_MS,
  type AuthError,
  authErrorCopy,
  confirmError,
  emailError,
  passwordError,
  safeNext,
} from '../auth/authRules'
import { useAuthStore } from '../auth/authStore'
import Button from '../components/ui/Button'
import Field from '../components/ui/Field'
import Input from '../components/ui/Input'

/**
 * §7.2 Sign-up — the same intake form as sign-in plus the confirm field. It states its real cost and
 * nothing it cannot back: the form asks for an address and a password, so that is all the copy claims
 * — no plan, no price, no billing line (PRODUCT.md §4; pricing is undecided).
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

  const show = (field: keyof typeof touched) => touched[field] || submitted
  const emailProblem = show('email') ? emailError(email) : null
  const passwordProblem = show('password') ? passwordError(password) : null
  const confirmProblem = show('confirm') ? confirmError(password, confirm) : null

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
        <h1 className="font-titling text-title text-ink">Open an office</h1>
        <p className="mt-1 text-body text-ink-2">An email and a password — no more is asked.</p>
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
          aria-invalid={emailProblem ? true : undefined}
        />
      </Field>

      <Field label="Password" hint={`At least ${MIN_PASSWORD} characters`} error={passwordProblem ?? undefined}>
        <Input
          id="signup-password"
          name="password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onBlur={() => setTouched((t) => ({ ...t, password: true }))}
          aria-invalid={passwordProblem ? true : undefined}
        />
      </Field>

      <Field label="Confirm password" error={confirmProblem ?? undefined}>
        <Input
          id="signup-confirm"
          name="confirm"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          onBlur={() => setTouched((t) => ({ ...t, confirm: true }))}
          aria-invalid={confirmProblem ? true : undefined}
        />
      </Field>

      {error && <CautionLine error={error} onRetry={submit} />}

      {redirectTo !== null ? (
        <IntakeStamp label="Office opened" />
      ) : (
        <Button type="submit" variant="primary" loading={submitting}>
          Open the office
        </Button>
      )}
    </form>
  )
}
