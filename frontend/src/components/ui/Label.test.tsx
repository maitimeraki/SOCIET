import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import { BANNED_TERMS, renderedText } from '../../test/copyLaw'
import Label from './Label'

describe('Label', () => {
  it('is the caps label — the label face, set in caps', () => {
    const html = renderToStaticMarkup(<Label>Documents</Label>)
    expect(html).toContain('text-label')
    expect(html).toContain('uppercase')
  })

  it('takes ink-3 on a light surface, and ink-2 on a ground-2 fill', () => {
    expect(renderToStaticMarkup(<Label>Documents</Label>)).toContain('text-ink-3')
    expect(renderToStaticMarkup(<Label tone="quiet">Documents</Label>)).toContain('text-ink-2')
  })

  it('gives the two tones different classes', () => {
    const quiet = renderToStaticMarkup(<Label tone="quiet">Documents</Label>)
    const plain = renderToStaticMarkup(<Label>Documents</Label>)
    expect(quiet).not.toBe(plain)
  })

  it('renders no banned word — the copy law holds over the kit', () => {
    const html = renderToStaticMarkup(<Label>Documents</Label>)
    expect(renderedText(html)).not.toMatch(BANNED_TERMS)
  })

  it('keeps the element a site already had, so the sweep changes no structure', () => {
    const heading = renderToStaticMarkup(<Label as="h3">Provenance</Label>)
    expect(heading.startsWith('<h3')).toBe(true)
    expect(heading).toContain('Provenance')
    const para = renderToStaticMarkup(<Label as="p">For</Label>)
    expect(para.startsWith('<p')).toBe(true)
  })

  it('carries a form control’s id when it is the label itself', () => {
    expect(renderToStaticMarkup(<Label as="label" htmlFor="society-question">Your question</Label>)).toContain('for="society-question"')
  })
})
