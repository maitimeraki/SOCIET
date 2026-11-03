import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): static markup in Node.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { Role } from '../api/types'
import { BANNED_TERMS, renderedText } from '../test/copyLaw'
import { RoleGuardView } from './RequireRole'

const render = (role: Role | null) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <RoleGuardView role={role} roles={['admin']}>
        <p>the admin surface</p>
      </RoleGuardView>
    </MemoryRouter>,
  )

describe('RoleGuardView — the role gate', () => {
  it('renders the guarded surface for an allowed role', () => {
    expect(render('admin')).toContain('the admin surface')
  })

  it('renders the 403 page for a signed-in visitor without the role', () => {
    const html = render('user')
    // SSR escapes the apostrophe in "don't", so match the invariant words.
    expect(html).toContain('have access to this page')
    expect(html).not.toContain('the admin surface')
  })

  it('never redirects to sign-in — a 403 is the answer', () => {
    const html = render('user')
    expect(html).toContain('href="/overview"')
    expect(html).not.toContain('/auth/signin')
  })

  it('treats a missing role as denied, never as a redirect', () => {
    const html = render(null)
    expect(html).toContain('have access to this page')
    expect(html).not.toContain('/auth/signin')
  })

  it('speaks the copy law on the 403 page', () => {
    expect(renderedText(render('user'))).not.toMatch(BANNED_TERMS)
  })
})
