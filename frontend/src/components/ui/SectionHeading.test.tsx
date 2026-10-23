import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import SectionHeading from './SectionHeading'

describe('SectionHeading', () => {
  it('takes the level the caller asks for', () => {
    expect(renderToStaticMarkup(<SectionHeading title="Your decisions" />)).toContain('<h2')
    expect(renderToStaticMarkup(<SectionHeading level={3} title="Your decisions" />)).toContain('<h3')
  })

  it('sets the title in the section title face', () => {
    expect(renderToStaticMarkup(<SectionHeading title="Your decisions" />)).toContain('text-title')
  })

  it('carries the lead when there is one, and nothing when there is not', () => {
    const withLead = renderToStaticMarkup(<SectionHeading title="Your decisions" lead="One line." />)
    expect(withLead).toContain('One line.')
    expect(renderToStaticMarkup(<SectionHeading title="Your decisions" />)).not.toContain('<p')
  })

  it('closes the block with the kit’s own rule, and only when asked', () => {
    expect(renderToStaticMarkup(<SectionHeading title="Your decisions" rule />)).toContain('rule-b')
    expect(renderToStaticMarkup(<SectionHeading title="Your decisions" />)).not.toContain('rule-b')
  })
})
