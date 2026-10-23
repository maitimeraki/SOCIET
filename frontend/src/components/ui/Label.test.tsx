import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
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
})
