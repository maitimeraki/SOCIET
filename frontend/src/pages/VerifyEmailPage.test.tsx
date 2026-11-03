import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): static markup in Node.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { BANNED_TERMS, renderedText } from '../test/copyLaw'
import VerifyEmailPage, { VerifyEmailView, type VerifyState } from './VerifyEmailPage'

const renderView = (state: VerifyState) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <VerifyEmailView state={state} />
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

  it('says the link failed and offers a new one', () => {
    const html = renderView('invalid')
    expect(html).toContain('This link is invalid or has expired')
    expect(html).toContain('href="/auth/forgot"')
  })

  it('treats a missing token as an explanatory error, never a blank page', () => {
    expect(renderWithoutToken()).toContain('This link is invalid or has expired')
  })

  it('announces the wait while the link is checked', () => {
    expect(renderView('checking')).toContain('role="status"')
  })

  it('speaks the copy law in every state', () => {
    for (const state of ['checking', 'success', 'invalid'] as const) {
      expect(renderedText(renderView(state))).not.toMatch(BANNED_TERMS)
    }
  })
})
