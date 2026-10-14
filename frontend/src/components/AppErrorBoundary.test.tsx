import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see GraphCanvas.test.tsx): the fallback is rendered to
// static markup in Node, and the boundary's catch is exercised through its React contract method.
import { renderToStaticMarkup } from 'react-dom/server'
import { AppErrorBoundary, AppErrorFallback, errorDigest } from './AppErrorBoundary'

const render = (error: unknown) =>
  renderToStaticMarkup(<AppErrorFallback error={error} onReload={() => {}} onBack={() => {}} />)

describe('AppErrorBoundary', () => {
  it('swaps the crashed child for the fallback state when a child throws', () => {
    const boom = new Error('render exploded')
    expect(AppErrorBoundary.getDerivedStateFromError(boom).error).toBe(boom)
  })

  it('still catches a throw that is not an Error, so the tree never blanks', () => {
    expect(AppErrorBoundary.getDerivedStateFromError(undefined).error).toBeInstanceOf(Error)
  })
})

describe('AppErrorFallback', () => {
  it('renders a recovery panel instead of an empty tree', () => {
    const html = render(new Error('render exploded'))
    expect(html).toContain('Something went wrong')
    expect(html).toContain('role="alert"')
  })

  it('offers reload and back-to-dashboard actions', () => {
    const html = render(new Error('render exploded'))
    expect(html).toContain('Reload')
    expect(html).toContain('Back to dashboard')
    expect(html.match(/<button/g)).toHaveLength(2)
  })

  it('shows the digest and never a stack trace', () => {
    const html = render(new Error('render exploded'))
    expect(html).toContain('Error: render exploded')
    expect(html).not.toContain('AppErrorFallback.test')
  })
})

describe('errorDigest', () => {
  it('keeps the error name and the first line of a multi-line message', () => {
    expect(errorDigest(new TypeError('first line\nsecond line'))).toBe('TypeError: first line')
  })

  it('falls back to the value itself for a non-Error throw', () => {
    expect(errorDigest('plain string')).toBe('plain string')
  })
})
