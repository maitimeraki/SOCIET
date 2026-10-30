import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import { BANNED_WORD, renderedText } from '../../test/copyLaw'
import Card from './Card'

describe('Card', () => {
  it('is an object: the canvas, one soft shadow, and no border at all', () => {
    const html = renderToStaticMarkup(<Card>body</Card>)
    expect(html).toContain('bg-paper')
    expect(html).toContain('shadow-card')
    expect(html).not.toMatch(/border(-[trblxy])?-/)
  })

  it('takes the Quiet Room card by default — 24px inside, a 16px corner', () => {
    const html = renderToStaticMarkup(<Card>body</Card>)
    expect(html).toContain('p-6')
    expect(html).toContain('rounded-lg')
  })

  it('pads by the number the caller asks for', () => {
    expect(renderToStaticMarkup(<Card pad={16}>body</Card>)).toContain('p-4')
    expect(renderToStaticMarkup(<Card pad={24}>body</Card>)).toContain('p-6')
  })

  it('rounds by the radius the caller asks for', () => {
    expect(renderToStaticMarkup(<Card radius="md">body</Card>)).toContain('rounded-md')
    expect(renderToStaticMarkup(<Card radius="lg">body</Card>)).toContain('rounded-lg')
  })

  it('lifts the object on hover only when it is asked to', () => {
    expect(renderToStaticMarkup(<Card hover>body</Card>)).toContain('hover:shadow-sheet')
    expect(renderToStaticMarkup(<Card>body</Card>)).not.toContain('hover:shadow-sheet')
  })

  it('renders the element the caller asks for', () => {
    expect(renderToStaticMarkup(<Card as="article">body</Card>)).toContain('<article')
    expect(renderToStaticMarkup(<Card as="li">body</Card>)).toContain('<li')
  })

  it('renders no banned word — the copy law holds over the kit', () => {
    const html = renderToStaticMarkup(<Card>Documents</Card>)
    expect(renderedText(html)).not.toMatch(BANNED_WORD)
  })
})
