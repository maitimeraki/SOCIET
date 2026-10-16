import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): the pure logic is tested
// directly and the components are rendered to static markup in Node.
import { renderToStaticMarkup } from 'react-dom/server'
import { ApiError, NetworkError } from '../api/rest'
import { CautionLine, IntakeStamp } from './authForm'
import { authErrorCopy, confirmError, emailError, passwordError, safeNext } from './authRules'

describe('authForm — validation on blur and submit', () => {
  it('rejects a blank or malformed email and accepts a shaped one', () => {
    expect(emailError('')).toBe('Enter your email address.')
    expect(emailError('   ')).toBe('Enter your email address.')
    expect(emailError('nope')).toBe('Enter a valid email address.')
    expect(emailError('owner@example.com')).toBeNull()
  })

  it('requires a password of at least eight characters', () => {
    expect(passwordError('')).toBe('Enter a password.')
    expect(passwordError('short')).toBe('Use at least 8 characters.')
    expect(passwordError('longenough')).toBeNull()
  })

  it('requires the confirm field to match the password', () => {
    expect(confirmError('longenough', '')).toBe('Re-enter your password.')
    expect(confirmError('longenough', 'different')).toBe('Passwords do not match.')
    expect(confirmError('longenough', 'longenough')).toBeNull()
  })
})

describe('authForm — the error states', () => {
  it('maps a 401 to one generic sentence and never names the field', () => {
    const copy = authErrorCopy(new ApiError(401, 'invalid credentials'), 'signin')
    expect(copy.message).toBe('Email or password is incorrect.')
    expect(copy.retry).toBe(false)
  })

  it('maps a 409 on sign-up to the taken-email sentence', () => {
    const copy = authErrorCopy(new ApiError(409, 'exists'), 'signup')
    expect(copy.message).toBe('That email is already registered.')
    expect(copy.retry).toBe(false)
  })

  it('offers a retry for a network failure, not for a credentials failure', () => {
    expect(authErrorCopy(new NetworkError(), 'signin').retry).toBe(true)
    expect(authErrorCopy(new NetworkError(), 'signup').retry).toBe(true)
    expect(authErrorCopy(new ApiError(401, 'x'), 'signin').retry).toBe(false)
  })

  it('does not fabricate a field-specific message for any other status', () => {
    const copy = authErrorCopy(new ApiError(500, 'boom'), 'signin')
    expect(copy.message).toBe('Something went wrong. Please try again.')
    expect(copy.retry).toBe(true)
  })
})

describe('authForm — `next` is a same-origin boundary', () => {
  it('honours a relative path and defaults everything else to the dashboard', () => {
    expect(safeNext('/runs/abc')).toBe('/runs/abc')
    expect(safeNext('/runs/abc?tab=verdict')).toBe('/runs/abc?tab=verdict')
    expect(safeNext(null)).toBe('/dashboard')
    expect(safeNext(undefined)).toBe('/dashboard')
    expect(safeNext('')).toBe('/dashboard')
  })

  it('rejects absolute, protocol-relative, backslash and bare-relative values', () => {
    expect(safeNext('https://evil.example/steal')).toBe('/dashboard')
    expect(safeNext('//evil.example/steal')).toBe('/dashboard')
    expect(safeNext('/\\evil.example')).toBe('/dashboard')
    expect(safeNext('runs/abc')).toBe('/dashboard')
  })

  it('rejects control characters the URL parser would strip into an off-site host (F1)', () => {
    // The WHATWG URL parser strips tab/newline/CR anywhere, so `/\n/evil.example` normalises to
    // `//evil.example` → an off-site origin. Layer 1 (control chars) rejects it; layer 2 (origin
    // equality) would catch it again as defence in depth.
    expect(safeNext('/\n/evil.example')).toBe('/dashboard')
    expect(safeNext('/\t/evil.example')).toBe('/dashboard')
    // A trailing CR is stripped to a same-origin path, so only layer 1 catches this one.
    expect(safeNext('/runs/abc\r')).toBe('/dashboard')
    // A `?next=` percent-encoded for a protocol-relative path is decoded before it reaches here:
    // `%2F%2Fevil.example` → `//evil.example`, and `/%2F%2Fevil.example` → `///evil.example`.
    expect(safeNext('//evil.example')).toBe('/dashboard')
    expect(safeNext('///evil.example')).toBe('/dashboard')
  })
})

describe('§7.2 marks — brass is the mark, ink is the word (R35)', () => {
  it('draws the caution line in brass with the words in ink', () => {
    const html = renderToStaticMarkup(
      <CautionLine error={{ message: 'Email or password is incorrect.', retry: false }} onRetry={() => {}} />,
    )
    expect(html).toContain('border-brass')
    expect(html).toContain('text-ink-2')
    expect(html).not.toContain('text-brass')
    expect(html).toContain('role="alert"')
  })

  it('offers a retry only when the failure is retryable', () => {
    const retryable = renderToStaticMarkup(
      <CautionLine error={{ message: 'offline', retry: true }} onRetry={() => {}} />,
    )
    expect(retryable).toContain('Try again')
    const fatal = renderToStaticMarkup(<CautionLine error={{ message: 'bad', retry: false }} onRetry={() => {}} />)
    expect(fatal).not.toContain('Try again')
  })

  it('lands the intake stamp with a brass mark and an ink label', () => {
    const html = renderToStaticMarkup(<IntakeStamp label="Signed in" />)
    expect(html).toContain('border-brass')
    expect(html).toContain('text-ink')
    expect(html).not.toContain('text-brass')
    expect(html).toContain('role="status"')
    expect(html).toContain('Signed in')
  })
})
