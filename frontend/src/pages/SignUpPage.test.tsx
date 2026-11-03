import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): the components are
// rendered to static markup in Node.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { BANNED_TERMS, renderedText } from '../test/copyLaw'
import { consentError } from '../auth/authRules'
import SignUpPage from './SignUpPage'

const render = () =>
  renderToStaticMarkup(
    <MemoryRouter>
      <SignUpPage />
    </MemoryRouter>,
  )

const page = render()

describe('the sign-up surface', () => {
  it('asks for two fields and says what happens to the material', () => {
    const html = render()
    expect(html).toContain('Start your first decision')
    expect(html).toContain('Your documents stay on the machine you start it on.')
  })

  it('offers no social sign-in until a provider is configured', () => {
    const html = render()
    expect(html).not.toContain('Continue with Google')
    expect(html).not.toContain('Continue with GitHub')
  })
})

describe('SignUpPage — the door in (§7.2)', () => {
  it('opens in the display face, in the first-decision voice', () => {
    expect(page).toContain('font-display text-display')
    expect(page).toContain('Start your first decision')
  })

  it('offers one door label', () => {
    expect(page).toMatch(/<button[^>]*>Create account<\/button>/)
    expect(page.match(/type="submit"/g)?.length).toBe(1)
  })

  it('states the cost once, and only here', () => {
    expect(page.match(/Free to start/g)?.length).toBe(1)
    expect(page).toContain('Free to start · No card')
    expect(page).not.toContain('Free to use')
    expect(page).not.toMatch(/no tier/i)
  })

  it('asks for email and password — labels above, no name or confirm field', () => {
    expect(page).toContain('id="signup-email"')
    expect(page).toContain('id="signup-password"')
    // The backend accepts email and password only; a name field would be silently discarded (R67).
    expect(page).not.toContain('signup-name')
    expect(page).not.toContain('signup-confirm')
    // Only one of the two fields is a password, so only one reveal control.
    expect(page.match(/aria-label="Show password"/g)?.length).toBe(1)
    // The labels sit above controls that are 48px high and bound by the label.
    expect(page).toMatch(/<label[^>]*>[\s\S]*?Email[\s\S]*?<\/label>/)
    expect(page).toContain('h-12')
    expect(page).toContain('for="signup-password"')
  })

  it('is not busy, invalid or alerting before a submit', () => {
    expect(page).toContain('aria-busy="false"')
    expect(page).not.toContain('role="alert"')
    expect(page).not.toContain('aria-invalid')
  })

  it('puts the trust line under the form, after the action and the switch', () => {
    const action = page.indexOf('Create account')
    const trust = page.indexOf('Your documents stay on the machine you start it on.')
    expect(action).toBeGreaterThan(-1)
    expect(trust).toBeGreaterThan(action)
  })

  it('cross-links to the other door', () => {
    expect(page).toContain('Already have an account?')
    expect(page).toContain('href="/auth/signin"')
  })

  it('renders no banned word and no retired vocabulary', () => {
    const text = renderedText(page)
    expect(text).not.toMatch(BANNED_TERMS)
    expect(text).not.toMatch(/survey/i)
  })
})

describe('SignUpPage — the consent attestations (Task 10)', () => {
  it('renders both required checkboxes, with their policy links', () => {
    const html = render()
    expect(html).toContain('id="signup-terms"')
    expect(html).toContain('id="signup-age"')
    expect(html).toContain('href="/terms"')
    expect(html).toContain('href="/privacy"')
    expect(html).toContain('I am 18 or older.')
  })

  it('blocks a signup until both are checked', () => {
    expect(consentError(false, false)).not.toBeNull()
    expect(consentError(true, false)).not.toBeNull()
    expect(consentError(false, true)).not.toBeNull()
    expect(consentError(true, true)).toBeNull()
  })
})
