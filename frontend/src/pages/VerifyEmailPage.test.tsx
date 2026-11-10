import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): static markup in Node.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { BANNED_TERMS, renderedText } from '../test/copyLaw'
import VerifyEmailPage, {
  VerifyEmailView,
  type ResendState,
  type VerifyState,
} from './VerifyEmailPage'

const renderView = (state: VerifyState, resend: ResendState = 'idle') =>
  renderToStaticMarkup(
    <MemoryRouter>
      <VerifyEmailView state={state} resend={resend} />
    </MemoryRouter>,
  )

/** The real page at `/auth/verify` with no `?token=`, so the initial state is the error. */
const renderWithoutToken = () =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={['/auth/verify']}>
      <Routes>
        <Route path="/auth/verify" element={<VerifyEmailPage />} />
      </Routes>
    </MemoryRouter>,
  )

describe('VerifyEmailPage — the confirmation link', () => {
  it('confirms the address and offers the sign-in door', () => {
    const html = renderView('success')
    expect(html).toContain('Your email is confirmed')
    expect(html).toContain('href="/auth/signin"')
  })

  it('says the link failed and offers a real resend, not the password-reset flow', () => {
    const html = renderView('invalid')
    expect(html).toContain('This link is invalid or has expired')
    expect(html).toContain('Send a new link')
    expect(html).not.toContain('/auth/forgot')
  })

  it('treats a missing token as an explanatory error, never a blank page', () => {
    expect(renderWithoutToken()).toContain('This link is invalid or has expired')
  })

  it('shows the sent confirmation after a resend', () => {
    const html = renderView('invalid', 'sent')
    expect(html).toContain('A new link is on its way.')
    expect(html).not.toContain('Send a new link')
  })

  it('offers a sign-in link carrying the return path when the resend needs a session', () => {
    const html = renderView('invalid', 'needs-signin')
    expect(html).toContain('Sign in to send yourself a new link.')
    expect(html).toContain('href="/auth/signin?next=%2Fauth%2Fverify"')
  })

  it('keeps a failed resend retryable', () => {
    expect(renderView('invalid', 'failed')).toContain('Try again')
  })

  it('announces the wait while the link is checked', () => {
    expect(renderView('checking')).toContain('role="status"')
  })

  it('never reports a connectivity failure as an invalid link', () => {
    const html = renderView('error')
    expect(html).toContain('check this link')
    expect(html).toContain('Try again')
    expect(html).not.toContain('invalid or has expired')
  })

  it('speaks the copy law in every state', () => {
    const states: [VerifyState, ResendState?][] = [
      ['checking'],
      ['success'],
      ['invalid'],
      ['invalid', 'sent'],
      ['invalid', 'needs-signin'],
      ['invalid', 'failed'],
      ['error'],
    ]
    for (const [state, resend] of states) {
      expect(renderedText(renderView(state, resend))).not.toMatch(BANNED_TERMS)
    }
  })
})
