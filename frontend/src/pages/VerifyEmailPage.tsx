import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { authVerify } from '../api/rest'
import { inlineLinkClasses } from '../components/ui/Button'

/** The three states the page can show; the pure view takes one as a prop. */
export type VerifyState = 'checking' | 'success' | 'invalid'

const LINK = `${inlineLinkClasses} font-ui text-body text-accent underline underline-offset-4`

export function VerifyEmailView({ state }: { state: VerifyState }) {
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
  return (
    <>
      <h1 className="font-display text-display font-medium tracking-[-0.03em] text-ink">
        This link is invalid or has expired
      </h1>
      <p className="mt-3 text-body text-ink-2">Request a new link and we'll send another.</p>
      <Link to="/auth/forgot" className={`${LINK} mt-6`}>
        Request a new link
      </Link>
    </>
  )
}

/**
 * `/auth/verify?token=…` — the confirmation link's landing. A missing token is an explanatory error,
 * never a silent no-op. The call runs once per token; the server is the only authority on validity.
 */
export default function VerifyEmailPage() {
  const [params] = useSearchParams()
  const token = params.get('token')
  const [state, setState] = useState<VerifyState>(token ? 'checking' : 'invalid')

  useEffect(() => {
    if (!token) return
    let cancelled = false
    authVerify(token)
      .then(() => {
        if (!cancelled) setState('success')
      })
      .catch(() => {
        if (!cancelled) setState('invalid')
      })
    return () => {
      cancelled = true
    }
  }, [token])

  return <VerifyEmailView state={state} />
}
