import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): the components are
// rendered to static markup in Node.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import SignUpPage from './SignUpPage'

const page = renderToStaticMarkup(
  <MemoryRouter>
    <SignUpPage />
  </MemoryRouter>,
)

describe('SignUpPage — the door in (§14.2)', () => {
  it('names the act of opening an account, not a room', () => {
    expect(page).toContain('Create your account')
    expect(page).toContain('An email and a password — no more is asked.')
  })

  it('offers one door label', () => {
    expect(page).toMatch(/<button[^>]*>Start free<\/button>/)
  })

  it('states the cost once, and only here', () => {
    expect(page.match(/Free to use/g)?.length).toBe(1)
    expect(page).toContain('Free to use. No account card, no trial, no tier.')
  })

  it('asks for three fields and offers a toggle on each of the two passwords', () => {
    expect(page).toContain('id="signup-email"')
    expect(page).toContain('id="signup-password"')
    expect(page).toContain('id="signup-confirm"')
    expect(page.match(/aria-label="Show password"/g)?.length).toBe(2)
  })

  it('is not busy, invalid or alerting before a submit', () => {
    expect(page).toContain('aria-busy="false"')
    expect(page).not.toContain('role="alert"')
    expect(page).not.toContain('aria-invalid')
  })

  it('cross-links to the other door', () => {
    expect(page).toContain('Already have an account?')
    expect(page).toContain('href="/auth/signin"')
  })
})
