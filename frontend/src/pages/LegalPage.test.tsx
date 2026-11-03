import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo: render to static markup in Node. MemoryRouter is
// required because the page's way out is a `<Link>`.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { ApiError } from '../api/rest'
import type { LegalDocument } from '../api/types'
import { BANNED_TERMS, copyLawApplies, isLegalPath, renderedText } from '../test/copyLaw'
import { LegalIndexView } from './LegalIndexPage'
import { isNotFoundError, LegalPageView, splitLegalContent } from './LegalPage'

const DOC: LegalDocument = {
  slug: 'privacy',
  version: '2026-11-03',
  effective_at: '2026-11-03',
  content_sha256: 'abc123',
  content:
    '> Draft for counsel review. Not legal advice.\n\n# Privacy Policy\n\nWe use a model, a token and an agent to read your material.\n',
}

const render = (props: Partial<Parameters<typeof LegalPageView>[0]>) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <LegalPageView doc={null} loading={false} failed={false} {...props} />
    </MemoryRouter>,
  )

describe('LegalPageView', () => {
  it('renders the served title, version, effective date and body', () => {
    const html = render({ doc: DOC })
    expect(html).toContain('Privacy Policy')
    expect(html).toContain('Version 2026-11-03')
    expect(html).toContain('Effective 3 Nov 2026')
    expect(html).toContain('We use a model, a token and an agent to read your material.')
    // The heading is not duplicated into the body.
    expect(html.match(/Privacy Policy/g)).toHaveLength(1)
  })

  it('shows the skeleton while loading', () => {
    const html = render({ loading: true })
    expect(html).toContain('aria-busy="true"')
    expect(html).toContain('skeleton-shimmer')
    expect(html).not.toContain('Privacy Policy')
  })

  it('gives an unknown slug a friendly dead end, not the server-error state', () => {
    const html = render({ notFound: true })
    expect(html).toContain('The address may be mistyped')
    expect(html).not.toContain('border-danger')
  })

  it('shows the error state when the registry cannot be reached', () => {
    const html = render({ failed: true, onRetry: () => {} })
    expect(html).toContain('border-danger')
    expect(html).toContain('nothing was lost')
    expect(html).toContain('Try again')
  })

  it('maps a 404 to the not-found state, and every other failure to the error state', () => {
    expect(isNotFoundError(new ApiError(404, 'Legal document not found.'))).toBe(true)
    expect(isNotFoundError(new ApiError(500, 'boom'))).toBe(false)
    expect(isNotFoundError(new Error('network'))).toBe(false)
  })

  it('splits the first heading from the body, keeping the served text intact', () => {
    const { title, body } = splitLegalContent(DOC.content)
    expect(title).toBe('Privacy Policy')
    expect(body.startsWith('> Draft for counsel review.')).toBe(true)
    expect(body).not.toContain('# Privacy Policy')
  })
})

describe('the copy-law exemption is legal-route only', () => {
  it('allows statutory words on a legal route', () => {
    const html = render({ doc: DOC })
    // The served text says "model", "token" and "agent" — banned in product copy, lawful here.
    expect(BANNED_TERMS.test(renderedText(html))).toBe(true)
    expect(isLegalPath('/legal/privacy')).toBe(true)
    expect(copyLawApplies('/legal/privacy')).toBe(false)
  })

  it('still applies the law to every marketing surface', () => {
    expect(isLegalPath('/pricing')).toBe(false)
    expect(copyLawApplies('/pricing')).toBe(true)
    expect(BANNED_TERMS.test(renderedText('<p>a model and a token</p>'))).toBe(true)
  })
})

describe('LegalIndexView', () => {
  it('lists each document with its version and effective date', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <LegalIndexView
          documents={[
            { slug: 'privacy', version: '2026-11-03', effective_at: '2026-11-03', content_sha256: 'a' },
            { slug: 'terms', version: '2026-11-03', effective_at: '2026-11-03', content_sha256: 'b' },
          ]}
          loading={false}
          failed={false}
        />
      </MemoryRouter>,
    )
    expect(html).toContain('href="/legal/privacy"')
    expect(html).toContain('href="/legal/terms"')
    expect(html).toContain('Privacy')
    expect(html).toContain('Terms')
    expect(html).toContain('Effective 3 Nov 2026')
  })
})
