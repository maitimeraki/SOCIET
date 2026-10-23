import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): the primitive renders
// to static markup in Node.
import { renderToStaticMarkup } from 'react-dom/server'
import ErrorState from './ErrorState'

describe('ErrorState', () => {
  it('states the failure and the server’s own detail', () => {
    const html = renderToStaticMarkup(
      <ErrorState title="Couldn't reach the server" detail="The uploads service is unavailable." />,
    )
    expect(html).toContain('Couldn&#x27;t reach the server')
    expect(html).toContain('The uploads service is unavailable.')
  })

  it('renders no retry unless the caller can recover', () => {
    expect(renderToStaticMarkup(<ErrorState title="Failed" />)).not.toContain('Try again')
  })

  it('renders the retry with a 44px tap target (§14.5 row 10)', () => {
    const html = renderToStaticMarkup(<ErrorState title="Failed" onRetry={() => {}} />)
    expect(html).toContain('Try again')
    expect(html).toMatch(/<button[^>]*class="[^"]*min-h-11/)
  })

  it('takes the surface’s own retry label', () => {
    const html = renderToStaticMarkup(
      <ErrorState title="Failed" onRetry={() => {}} retryLabel="Reload this section" />,
    )
    expect(html).toContain('Reload this section')
    expect(html).not.toContain('Try again')
  })

  it('keeps any extra actions beside the retry', () => {
    const html = renderToStaticMarkup(
      <ErrorState title="Failed" onRetry={() => {}} actions={<a href="/help">Read the guide</a>} />,
    )
    expect(html).toContain('Read the guide')
    expect(html).toContain('Try again')
  })
})
