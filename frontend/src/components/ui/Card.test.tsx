import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import Card from './Card'

describe('Card', () => {
  it('is an object: the canvas, one soft shadow, and no border at all', () => {
    const html = renderToStaticMarkup(<Card>body</Card>)
    expect(html).toContain('bg-canvas')
    expect(html).toContain('shadow-raised')
    expect(html).not.toMatch(/border(-[trblxy])?-/)
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
    expect(renderToStaticMarkup(<Card hover>body</Card>)).toContain('hover:shadow-floating')
    expect(renderToStaticMarkup(<Card>body</Card>)).not.toContain('hover:shadow-floating')
  })

  it('renders the element the caller asks for', () => {
    expect(renderToStaticMarkup(<Card as="article">body</Card>)).toContain('<article')
    expect(renderToStaticMarkup(<Card as="li">body</Card>)).toContain('<li')
  })
})
