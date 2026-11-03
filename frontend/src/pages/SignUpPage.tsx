import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { SIGN_UP, TRUST_LINE } from '../auth/authCopy'
import { CautionLine, IntakeStamp, PasswordField } from '../auth/authForm'
import {
  MIN_PASSWORD,
  STAMP_MS,
  type AuthError,
  authErrorCopy,
  consentError,
  emailError,
  fieldProblem,
  nextSuffix,
  passwordError,
  safeNext,
} from '../auth/authRules'
import { useAuthStore } from '../auth/authStore'
import Button from '../components/ui/Button'
import Field from '../components/ui/Field'
import Input from '../components/ui/Input'

/**
 * §7.2 / §14.2 Sign-up — the intake form on the sheet: a Fraunces title, email, password and the
 * two consent attestations the backend now requires, one primary action, and the one promise about
 * the material. The design's name field is deliberately absent: `SignupRequest` accepts no name,
 * and a field whose value is silently discarded would be a trust defect (R67).
 *
 * It states its real cost and nothing it cannot back (PRODUCT.md §4): `Free to start · No card`,
 * stated **once**, on this form only (D2).
 *
 * The invalid mark is the field's own 3px danger hatch — never a red box — and it is re-derived
 * from each field's current value, so it clears the moment that value becomes valid.
 */
export default function SignUpPage() {
  const signup = useAuthStore((s) => s.signup)
  const navigate = useNavigate()
  const [params] = useSearchParams()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [acceptTerms, setAcceptTerms] = useState(false)
  const [ageConfirmed, setAgeConfirmed] = useState(false)
  const [touched, setTouched] = useState({ email: false, password: false })
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
  const consentProblem = submitted ? consentError(acceptTerms, ageConfirmed) : null

  async function submit() {
    if (submitting || redirectTo !== null) return
    setSubmitted(true)
    setError(null)
    if (emailError(email) || passwordError(password) || consentError(acceptTerms, ageConfirmed)) return
    setSubmitting(true)
    try {
      await signup(email, password, acceptTerms, ageConfirmed) // sets the auth store on success
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
        <h1 className="font-display text-display font-medium tracking-[-0.03em] text-ink">
          {SIGN_UP.heading}
        </h1>
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

      <div className={`space-y-2.5 pl-2.5 ${consentProblem ? 'field-invalid' : ''}`}>
        <div className="flex min-h-11 items-start gap-2.5">
          <input
            id="signup-terms"
            name="accept_terms"
            type="checkbox"
            checked={acceptTerms}
            onChange={(e) => setAcceptTerms(e.target.checked)}
            disabled={submitting}
            aria-invalid={consentProblem ? true : undefined}
            className="mt-1 h-4 w-4 shrink-0 accent-accent"
          />
          <div className="text-body-sm text-ink-2">
            <label htmlFor="signup-terms">I agree to the </label>
            <Link to="/terms" className="underline underline-offset-4 hover:text-ink">Terms</Link>
            {' and '}
            <Link to="/privacy" className="underline underline-offset-4 hover:text-ink">Privacy Policy</Link>.
          </div>
        </div>
        <div className="flex min-h-11 items-start gap-2.5">
          <input
            id="signup-age"
            name="age_confirmed"
            type="checkbox"
            checked={ageConfirmed}
            onChange={(e) => setAgeConfirmed(e.target.checked)}
            disabled={submitting}
            aria-invalid={consentProblem ? true : undefined}
            className="mt-1 h-4 w-4 shrink-0 accent-accent"
          />
          <label htmlFor="signup-age" className="text-body-sm text-ink-2">
            I am 18 or older.
          </label>
        </div>
        {consentProblem && (
          <p role="alert" className="text-micro text-ink-2">
            {consentProblem}
          </p>
        )}
      </div>

      {error && <CautionLine error={error} onRetry={submit} />}

      {redirectTo !== null ? (
        <IntakeStamp label={SIGN_UP.stamp} />
      ) : (
        <Button type="submit" variant="primary" loading={submitting} className="max-lg:min-h-11">
          {SIGN_UP.action}
        </Button>
      )}

      <p className="text-pretty font-mono text-mono text-ink-3">{SIGN_UP.cost}</p>

      <p className="text-body text-ink-3">
        {SIGN_UP.crossQuestion}{' '}
        <Link
          to={`/auth/signin${nextSuffix(params)}`}
          className="inline-flex min-h-11 min-w-11 items-center font-ui text-body text-ink-2 underline decoration-ink-3 underline-offset-4 transition-colors duration-state hover:text-ink hover:decoration-accent lg:min-h-0 lg:min-w-0"
        >
          {SIGN_UP.crossAction}
        </Link>
      </p>

      <p className="border-t border-rule pt-4 text-body-sm text-ink-3">{TRUST_LINE}</p>
    </form>
  )
}
