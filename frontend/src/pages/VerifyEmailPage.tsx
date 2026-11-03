import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApiError, authVerify, authVerifySend } from '../api/rest'
import { signInTarget } from '../auth/guard'
import Button, { inlineLinkClasses } from '../components/ui/Button'

/** The states the link check can show; the pure view takes one as a prop. */
export type VerifyState = 'checking' | 'success' | 'invalid' | 'error'

/** The resend action's states: idle → sending → sent, or the two honest dead ends. */
export type ResendState = 'idle' | 'sending' | 'sent' | 'needs-signin' | 'failed'

const LINK = `${inlineLinkClasses} font-ui text-body text-accent underline underline-offset-4`

export function VerifyEmailView({
  state,
  resend = 'idle',
  onResend,
  onRetry,
}: {
  state: VerifyState
  resend?: ResendState
  onResend?: () => void
  onRetry?: () => void
}) {
  if (state === 'checking') {
    return <p role="status" className="text-body text-ink-2">Checking your link…</p>
  }
  if (state === 'success') {
    return (
      <>
        <h1 className="font-display text-display font-medium tracking-[-0.03em] text-ink">
          Your email is confirmed
        </h1>
        <p className="mt-3 text-body text-ink-2">Your account is ready.</p>
        <Link to="/auth/signin" className={`${LINK} mt-6`}>
          Sign in
        </Link>
      </>
    )
  }
  if (state === 'error') {
    return (
      <>
        <h1 className="font-display text-display font-medium tracking-[-0.03em] text-ink">
          Couldn't check this link
        </h1>
        <p className="mt-3 text-body text-ink-2">
          Your connection may have dropped. Nothing has changed — try again.
        </p>
        <Button type="button" variant="secondary" className="mt-4 min-h-11" onClick={onRetry}>
          Try again
        </Button>
      </>
    )
  }

  return (
    <>
      <h1 className="font-display text-display font-medium tracking-[-0.03em] text-ink">
        This link is invalid or has expired
      </h1>

      {resend === 'sent' ? (
        <p role="status" className="mt-3 text-body text-ink-2">
          A new link is on its way.
        </p>
      ) : resend === 'needs-signin' ? (
        <>
          <p className="mt-3 text-body text-ink-2">Sign in to send yourself a new link.</p>
          <Link to={signInTarget('/auth/verify', '')} className={`${LINK} mt-4`}>
            Sign in
          </Link>
        </>
      ) : (
        <>
          <p className="mt-3 text-body text-ink-2">
            {resend === 'failed'
              ? "Couldn't send a new link. Try again."
              : 'You can send yourself a new one.'}
          </p>
          <Button
            type="button"
            variant="secondary"
            className="mt-4 min-h-11"
            loading={resend === 'sending'}
            disabled={resend === 'sending'}
            onClick={onResend}
          >
            {resend === 'failed' ? 'Try again' : 'Send a new link'}
          </Button>
        </>
      )}
    </>
  )
}

/**
 * `/auth/verify?token=…` — the confirmation link's landing. A missing token is an explanatory
 * error. A 400 is a genuinely dead link; any other failure is a connectivity problem and stays
 * retryable — the page never reports a dropped connection as an invalid link.
 */
export default function VerifyEmailPage() {
  const [params] = useSearchParams()
  const token = params.get('token')
  const [state, setState] = useState<VerifyState>(token ? 'checking' : 'invalid')
  const [resend, setResend] = useState<ResendState>('idle')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!token) return
    let cancelled = false
    authVerify(token)
      .then(() => {
        if (!cancelled) setState('success')
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setState(err instanceof ApiError && err.status === 400 ? 'invalid' : 'error')
      })
    return () => {
      cancelled = true
    }
  }, [token, attempt])

  const resendLink = () => {
    setResend('sending')
    authVerifySend()
      .then(() => setResend('sent'))
      .catch((err: unknown) => {
        setResend(err instanceof ApiError && err.status === 401 ? 'needs-signin' : 'failed')
      })
  }

  return (
    <VerifyEmailView
      state={state}
      resend={resend}
      onResend={resendLink}
      onRetry={() => {
        setState('checking')
        setAttempt((n) => n + 1)
      }}
    />
  )
}
