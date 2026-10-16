import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): the components are
// rendered to static markup in Node. The form's shared rules and §7.2 marks are tested beside their
// module in `src/auth/authForm.test.tsx`.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import AuthLayout from '../auth/AuthLayout'
import SignInPage from './SignInPage'

describe('SignInPage — the rendered intake form (§7.2)', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <SignInPage />
    </MemoryRouter>,
  )

  it('renders the ruled-baseline fields and the route button', () => {
    expect(html).toContain('corner-tick') // Input's registration mark, on the control itself
    expect(html).toContain('type="email"')
    expect(html).toContain('type="password"')
    expect(html).toContain('Open the office')
  })

  it('is not busy, invalid or alerting before a submit', () => {
    expect(html).toContain('aria-busy="false"')
    expect(html).not.toContain('role="alert"')
    expect(html).not.toContain('aria-invalid')
  })
})

describe('AuthLayout — the front door frame (§7.2)', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AuthLayout />
    </MemoryRouter>,
  )

  it('is a main landmark carrying the wordmark and the thesis', () => {
    expect(html).toContain('<main')
    expect(html).toContain('Societas')
    expect(html).toContain('publishable sheet')
  })

  it('draws the sample sheet as decorative geometry behind an honest caption', () => {
    expect(html).toContain('A sample sheet, not a run')
    expect(html).toContain('aria-hidden="true"') // the drawn sample never carries meaning alone
  })

  it('carries no shell chrome — no app navigation', () => {
    expect(html).not.toContain('<nav')
  })
})
