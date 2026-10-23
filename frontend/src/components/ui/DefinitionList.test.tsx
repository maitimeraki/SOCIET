import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import { BANNED_WORD, renderedText } from '../../test/copyLaw'
import DefinitionList from './DefinitionList'

const ITEMS = [
  { term: 'core', value: 'the question as it was asked' },
  { term: 'keywords', value: 'lease, grease trap' },
]

describe('DefinitionList', () => {
  it('is a list of terms and their values', () => {
    const html = renderToStaticMarkup(<DefinitionList items={ITEMS} />)
    expect(html).toContain('<dl')
    expect(html).toContain('<dt')
    expect(html).toContain('<dd')
    expect(html).toContain('the question as it was asked')
  })

  it('is ruled — a record, never a card: a hairline and no shadow', () => {
    const html = renderToStaticMarkup(<DefinitionList items={ITEMS} />)
    expect(html).toContain('divide-rule')
    expect(html).not.toContain('shadow-')
  })

  it('takes the map’s own rule on the map’s own surface', () => {
    const dark = renderToStaticMarkup(<DefinitionList items={ITEMS} tone="dark" />)
    expect(dark).toContain('rule-dark')
    expect(dark).toContain('text-map-ink')
  })

  it('keeps the light ink on the light surface', () => {
    const light = renderToStaticMarkup(<DefinitionList items={ITEMS} />)
    expect(light).toContain('text-ink-3')
    expect(light).not.toContain('text-map-ink')
  })

  it('renders no banned word — the copy law holds over the kit', () => {
    const html = renderToStaticMarkup(<DefinitionList items={ITEMS} />)
    expect(renderedText(html)).not.toMatch(BANNED_WORD)
  })
})
