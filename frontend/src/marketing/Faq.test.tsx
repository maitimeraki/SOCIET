import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import Faq from './Faq'
import { sections } from './copy'

const html = renderToStaticMarkup(<Faq />)
const answers = sections.faq.items.map((item) => item.a).join(' ')

describe('questions owners ask — an accordion on ruled baselines', () => {
  it('renders every question as a disclosure', () => {
    for (const item of sections.faq.items) expect(html).toContain(item.q)
    expect(html.split('aria-expanded').length - 1).toBe(sections.faq.items.length)
  })

  it('opens the first answer and keeps the rest collapsed', () => {
    expect(html).toContain('aria-expanded="true"')
    expect(html).toContain('aria-expanded="false"')
    expect(html).toContain(sections.faq.items[0].a)
    expect(html).not.toContain(sections.faq.items[1].a)
  })

  it('answers from product behaviour, with no unverifiable claim', () => {
    expect(answers).not.toMatch(/over 100/i)
    expect(answers).not.toContain('LiteLLM')
    expect(answers).not.toMatch(/minute per ten/i)
    expect(answers).not.toContain('PDFs')
  })

  it('keeps the product truth in its answers', () => {
    expect(answers).toContain('no documents, no panel')
    expect(answers).toContain('opposing case')
    expect(answers).toContain('sources')
  })
})
