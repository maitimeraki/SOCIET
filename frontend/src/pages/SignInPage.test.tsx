import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): the components are
// rendered to static markup in Node. The form's shared rules and §7.2 marks are tested beside their
// module in `src/auth/authForm.test.tsx`.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { BANNED_TERMS, renderedText } from '../test/copyLaw'
import AuthLayout from '../auth/AuthLayout'
import SignInPage from './SignInPage'

const page = renderToStaticMarkup(
  <MemoryRouter>
    <SignInPage />
  </MemoryRouter>,
)

const frame = renderToStaticMarkup(
  <MemoryRouter>
    <AuthLayout />
  </MemoryRouter>,
)

describe('SignInPage — the door back in (§7.2)', () => {
  it('renders the Quiet Room fields and the door button', () => {
    expect(page).toContain('border-rule') // Input's record rule, on the control itself
    expect(page).toContain('type="email"')
    expect(page).toContain('type="password"')
    // The door label is the submit control's own text, not a page-wide substring the heading
    // already satisfies — a regression to another label must fail here.
    expect(page).toMatch(/<button[^>]*>Sign in<\/button>/)
    expect(page.match(/type="submit"/g)?.length).toBe(1)
  })

  it('welcomes the visitor back in the display face, and states what happens to the material', () => {
    expect(page).toContain('font-display text-display')
    expect(page).toContain('Welcome back')
    expect(page).toContain('Your documents stay on the machine you start it on.')
  })

  it('offers one recovery link, and no second primary action for it', () => {
    expect(page).toContain('Forgot password?')
    expect(page).toContain('href="mailto:hello@societas.example?subject=Password%20reset"')
  })

  it('is not busy, invalid or alerting before a submit', () => {
    expect(page).toContain('aria-busy="false"')
    expect(page).not.toContain('role="alert"')
    expect(page).not.toContain('aria-invalid')
  })

  it('offers the show/hide toggle as a real button, outside the field’s label', () => {
    expect(page).toContain('type="button"')
    expect(page).toContain('aria-label="Show password"')
    // A <label> activates the first labelable descendant, so the toggle must not sit inside one:
    // the label's text would fire it and its name would compete with the field's.
    const labels = page.match(/<label[\s\S]*?<\/label>/g) ?? []
    expect(labels.length).toBeGreaterThan(0)
    expect(labels.every((label) => !label.includes('<button'))).toBe(true)
  })

  it('binds the field’s name with htmlFor, so the control keeps its accessible name', () => {
    expect(page).toContain('for="signin-password"')
    expect(page).toContain('id="signin-password"')
  })

  it('cross-links to the other door', () => {
    expect(page).toContain('No account yet?')
    expect(page).toContain('Create an account')
    expect(page).toContain('href="/auth/signup"')
  })

  it('renders no banned word and no retired vocabulary', () => {
    const text = renderedText(page)
    expect(text).not.toMatch(BANNED_TERMS)
    expect(text).not.toMatch(/survey/i)
  })
})

describe('AuthLayout — the door frame (§7.2)', () => {
  it('is a main landmark carrying the wordmark and the thesis', () => {
    expect(frame).toContain('<main')
    expect(frame).toContain('Societas')
    expect(frame).toContain('Decision panel')
    expect(frame).toContain('A panel of experts reads your documents, argues the question, and files an answer.')
  })

  it('sets the form column at 420px, with 32px of paper around the form', () => {
    expect(frame).toContain('lg:grid-cols-[420px_1fr]')
    expect(frame).toContain('p-8')
  })

  it('stands the cropped filed decision beside the form, labelled a worked example', () => {
    expect(frame).toContain('aria-label="A worked example of a filed decision"')
    expect(frame).toContain('A filed decision · example')
    expect(frame).toContain('A worked example, prepared to show what a filed answer looks like.')
    expect(frame).toContain('Should Ridgeline Coffee open a second location on Mill Street this spring?')
    expect(frame).toContain('0.82')
    expect(frame).toContain('The case against')
    // Cropped to the filed fragment: the reasoning and the panel split are the full document's.
    expect(frame).not.toContain('The reasoning')
    expect(frame).not.toContain('Who held which view')
  })

  it('separates the two columns with one hairline, not a band', () => {
    expect(frame).toContain('rule-l')
    expect(frame).toContain('rule-t')
    expect(frame).not.toContain('<hr')
  })

  it('carries no shell chrome — no app navigation', () => {
    expect(frame).not.toContain('<nav')
  })
})
