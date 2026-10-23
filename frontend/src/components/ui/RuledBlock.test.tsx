import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import RuledBlock from './RuledBlock'

describe('RuledBlock', () => {
  it('renders the legend key beside the title, so the block keys to a Legend entry', () => {
    const html = renderToStaticMarkup(
      <RuledBlock legendKey="A" title="Stations">
        <p>nine stations fixed</p>
      </RuledBlock>,
    )
    expect(html).toContain('>A<')
    expect(html).toContain('Stations')
    expect(html).toContain('nine stations fixed')
  })

  it('is bounded top and bottom by hairlines, and is not an enclosed box', () => {
    const html = renderToStaticMarkup(<RuledBlock>body</RuledBlock>)
    expect(html).toContain('rule-y') // the kit's own rule, both sides
    expect(html).not.toContain('rounded-')
    expect(html).not.toContain('border-l')
    expect(html).not.toContain('border-r')
  })

  it('renders the children alone when there is no legend key and no title', () => {
    const html = renderToStaticMarkup(<RuledBlock>bare</RuledBlock>)
    expect(html).not.toContain('<header')
    expect(html).toContain('bare')
  })

  it('keeps the legend key readable to assistive tech — it is the accessibility key', () => {
    const html = renderToStaticMarkup(<RuledBlock legendKey="B">body</RuledBlock>)
    expect(html).not.toContain('aria-hidden')
  })
})
