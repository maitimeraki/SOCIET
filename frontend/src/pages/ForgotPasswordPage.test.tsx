import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): static markup in Node.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { BANNED_TERMS, renderedText } from '../test/copyLaw'
import ForgotPasswordPage, { ForgotPasswordSentView } from './ForgotPasswordPage'

const renderSent = () =>
  renderToStaticMarkup(
    <MemoryRouter>
      <ForgotPasswordSentView />
    </MemoryRouter>,
  )

const initial = renderToStaticMarkup(
  <MemoryRouter initialEntries={['/auth/forgot']}>
    <ForgotPasswordPage />
  </MemoryRouter>,
)

describe('ForgotPasswordPage — one answer, whether or not the address exists', () => {
  it('shows the same success copy for any submitted address', () => {
    expect(renderSent()).toContain('If that address has an account, a reset link is on its way.')
  })

  it('offers the way back to sign in', () => {
    expect(renderSent()).toContain('href="/auth/signin"')
  })

  it('starts on an email field with the primary action', () => {
    expect(initial).toContain('type="email"')
    expect(initial).toContain('Send reset link')
  })

  it('speaks the copy law', () => {
    expect(renderedText(renderSent())).not.toMatch(BANNED_TERMS)
    expect(renderedText(initial)).not.toMatch(BANNED_TERMS)
  })
})
