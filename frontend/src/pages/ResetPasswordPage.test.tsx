import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): static markup in Node.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ApiError } from '../api/rest'
import { BANNED_TERMS, renderedText } from '../test/copyLaw'
import ResetPasswordPage, {
  ResetPasswordView,
  confirmError,
  resetFailure,
  resetProblem,
} from './ResetPasswordPage'

const renderView = (state: 'success' | 'invalid', message?: string) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <ResetPasswordView state={state} message={message} />
    </MemoryRouter>,
  )

const renderWithoutToken = () =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={['/auth/reset']}>
      <Routes>
        <Route path="/auth/reset" element={<ResetPasswordPage />} />
      </Routes>
    </MemoryRouter>,
  )

describe('ResetPasswordPage — the new password', () => {
  it('rejects a password shorter than the existing minimum', () => {
    expect(resetProblem('short', 'short')).toBe('Use at least 8 characters.')
  })

  it('rejects a confirmation that differs from the password', () => {
    expect(resetProblem('longenough', 'different')).toBe("The two passwords don't match.")
    expect(confirmError('longenough', 'different')).toBe("The two passwords don't match.")
  })

  it('accepts matching values at or above the minimum', () => {
    expect(resetProblem('longenough', 'longenough')).toBeNull()
  })

  it('shows the changed state with the sign-in door', () => {
    const html = renderView('success')
    expect(html).toContain('Password changed')
    expect(html).toContain('href="/auth/signin"')
  })

  it('shows the server message when the link is invalid', () => {
    expect(renderView('invalid', 'This reset link has expired.')).toContain(
      'This reset link has expired.',
    )
  })

  it('treats a missing token as an invalid link', () => {
    expect(renderWithoutToken()).toContain('This link is invalid or has expired')
  })

  it('maps only the server’s 400/422 to the invalid-link view', () => {
    expect(resetFailure(new ApiError(400, 'This reset link has expired.'))).toEqual({
      invalid: true,
      message: 'This reset link has expired.',
    })
    expect(resetFailure(new ApiError(422, 'Use a stronger password.'))).toEqual({
      invalid: true,
      message: 'Use a stronger password.',
    })
  })

  it('leaves a server or network failure retryable, never a dead link', () => {
    expect(resetFailure(new ApiError(500, 'Internal error')).invalid).toBe(false)
    expect(resetFailure(new TypeError('offline')).invalid).toBe(false)
    expect(resetFailure(new TypeError('offline')).message).toContain("Couldn't reach the server")
  })

  it('speaks the copy law', () => {
    for (const html of [renderView('success'), renderView('invalid'), renderWithoutToken()]) {
      expect(renderedText(html)).not.toMatch(BANNED_TERMS)
    }
  })
})
