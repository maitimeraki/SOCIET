/// <reference types="node" />
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): the components are
// rendered to static markup in Node.
//
// The auth surface's acceptance, in one place: the copy law, the retired world, the cost line, the
// one filed sheet, the invalid mark's contrast, and the cascade the two forms' derivation must
// not have.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import AuthLayout from '../auth/AuthLayout'
import { emailError, fieldProblem, passwordError } from '../auth/authRules'
import SignInPage from '../pages/SignInPage'
import SignUpPage from '../pages/SignUpPage'
import { BANNED_WORD, renderedText } from './copyLaw'

/** The whole surface, frame and form together, as a visitor sees it. */
const surface = (path: 'signin' | 'signup') =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={[`/auth/${path}`]}>
      <Routes>
        <Route path="/auth" element={<AuthLayout />}>
          <Route path="signin" element={<SignInPage />} />
          <Route path="signup" element={<SignUpPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )

const signIn = surface('signin')
const signUp = surface('signup')

/** Every source file under a directory. */
function sourceFiles(dir: string): string[] {
  const found: string[] = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) found.push(...sourceFiles(full))
    else if (/\.(ts|tsx|css)$/.test(entry.name)) found.push(full)
  }
  return found
}

/** The retired world: the words the old surface spoke, in any file, comment included. */
const RETIRED = /survey|office|publishable|deliberation|specialist/i

describe('the auth surface speaks the new world', () => {
  it('renders no banned word, on either form or the frame', () => {
    expect(renderedText(signIn)).not.toMatch(BANNED_WORD)
    expect(renderedText(signUp)).not.toMatch(BANNED_WORD)
  })

  it('carries no retired-world word, in any file — a comment counts too', () => {
    const files = [
      ...sourceFiles('src/auth'),
      'src/pages/SignInPage.tsx',
      'src/pages/SignUpPage.tsx',
    ]
    const offenders = files.filter((file) => RETIRED.test(readFileSync(file, 'utf8')))
    expect(offenders).toEqual([])
  })

  it('states the cost once, on sign-up only', () => {
    expect(signIn.match(/Free to use/g)?.length ?? 0).toBe(0)
    expect(signUp.match(/Free to use/g)?.length ?? 0).toBe(1)
  })

  it('cross-links the two forms to each other', () => {
    expect(signIn).toContain('href="/auth/signup"')
    expect(signUp).toContain('href="/auth/signin"')
  })

  it('shows the wordmark’s descriptor at every width — the phone draws it too (§14.2)', () => {
    for (const html of [signIn, signUp]) {
      const descriptor = html.match(/<span class="([^"]*)">Decision panel<\/span>/)
      expect(descriptor).not.toBeNull()
      expect(descriptor![1].split(' ')).not.toContain('hidden')
    }
  })

  it('has one FiledSheet implementation, and the auth column renders it', () => {
    // A primitive is defined in a source file, never in a test — so the tests are out of the sweep.
    const definitions = sourceFiles('src').filter(
      (file) => !file.includes('.test.') && /export default function FiledSheet/.test(readFileSync(file, 'utf8')),
    )
    expect(definitions.map((file) => file.replace(/\\/g, '/'))).toEqual(['src/components/ui/FiledSheet.tsx'])
    expect(signIn).toContain('Worked example')
  })

  it('puts every field on Input’s ruled baseline, and no field in a box', () => {
    for (const html of [signIn, signUp]) {
      const inputs = html.match(/<input[^>]*>/g) ?? []
      expect(inputs.length).toBeGreaterThan(0)
      for (const input of inputs) {
        const classes = (input.match(/class="([^"]*)"/)?.[1] ?? '').split(' ')
        expect(classes).toContain('border-b')
        expect(classes).toContain('border-ink-3')
        expect(classes).toContain('bg-transparent')
        expect(classes).not.toContain('border') // no box around the field
        expect(classes.some((name) => name.startsWith('rounded'))).toBe(false)
      }
    }
  })

  it('gives the focus state its own visual — the accent rule and the corner tick', () => {
    for (const html of [signIn, signUp]) {
      expect(html).toContain('corner-tick')
      expect(html).toContain('focus:border-accent')
    }
  })
})

describe('the invalid mark is a hatch, and it is measured', () => {
  const css = readFileSync('src/index.css', 'utf8')

  const channel = (c: number) => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  const luminance = ([r, g, b]: number[]) =>
    0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
  const contrast = (a: number[], b: number[]) => {
    const x = luminance(a)
    const y = luminance(b)
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05)
  }
  const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16))
  const token = (name: string) => rgb(css.match(new RegExp(`${name}:\\s*(#[0-9a-f]{6})`, 'i'))![1])

  it('never turns the control’s own rule red', () => {
    // The invalid state is the field’s left margin hatch. A red baseline on top of it would be the
    // red box the craft floor refuses, so the control keeps its --ink-3 rule either way.
    expect(readFileSync('src/components/ui/Input.tsx', 'utf8')).not.toContain('border-danger')
  })

  it('draws the hatch clear of 3:1 against the sheet', () => {
    const gradient = css.match(
      /repeating-linear-gradient\(-45deg, var\(--color-danger\) 0 (\d+)px, transparent 0 (\d+)px\)/,
    )
    expect(gradient).toBeTruthy()
    // The hatch is not a flat colour: the paint is the coverage-weighted mix of the stripe and the
    // sheet, and the contrast is taken on that composite.
    const coverage = Number(gradient![1]) / Number(gradient![2])
    const stripe = token('--color-danger')
    const sheet = token('--color-paper')
    const paint = stripe.map((c, i) => c * coverage + sheet[i] * (1 - coverage))
    expect(contrast(paint, sheet)).toBeGreaterThanOrEqual(3)
  })
})

describe('the invalid state is re-derived from the field’s own value', () => {
  it('clears the moment that field’s value becomes valid — a paste, not a keystroke', () => {
    expect(fieldProblem('nope', true, false, emailError)).toBe('Enter a valid email address.')
    // The value changes with no keystroke at all — a paste, an autofill, a script.
    expect(fieldProblem('owner@example.com', true, false, emailError)).toBeNull()
  })

  it('does not leave the other fields red once they are corrected', () => {
    const submitted = true
    expect(fieldProblem('owner@example.com', true, submitted, emailError)).toBeNull()
    expect(fieldProblem('short', true, submitted, passwordError)).toBe('Use at least 8 characters.')
  })

  it('shows no mark on a field nobody has touched, until a submit', () => {
    expect(fieldProblem('', false, false, emailError)).toBeNull()
    expect(fieldProblem('', false, true, emailError)).toBe('Enter your email address.')
  })
})
