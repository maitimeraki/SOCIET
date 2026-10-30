import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import EmptyState from './EmptyState'

describe('EmptyState', () => {
  it('renders the headline above the sentence when a title is given', () => {
    const html = renderToStaticMarkup(
      <EmptyState title="Start with your material" line="Everything else follows from it." />,
    )
    expect(html).toContain('font-display text-heading text-ink')
    expect(html.indexOf('Start with your material')).toBeLessThan(
      html.indexOf('Everything else follows from it.'),
    )
  })

  it('still renders the sentence alone when no title is given', () => {
    const html = renderToStaticMarkup(<EmptyState line="Everything else follows from it." />)
    expect(html).toContain('Everything else follows from it.')
    expect(html).not.toContain('font-display text-heading')
  })

  it('keeps the caller’s one action beside the block', () => {
    const html = renderToStaticMarkup(
      <EmptyState line="Everything else follows from it." action={<button type="button">Add a document</button>} />,
    )
    expect(html).toContain('Add a document')
  })
})
