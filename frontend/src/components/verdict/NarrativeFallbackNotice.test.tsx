import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import NarrativeFallbackNotice, { NARRATIVE_FALLBACK_COPY } from './NarrativeFallbackNotice'

const render = (status: string) => renderToStaticMarkup(<NarrativeFallbackNotice status={status} />)

describe('NarrativeFallbackNotice — the narrative fallback notice (§17.3)', () => {
  it('carries the exact required copy when narrative_status is fallback', () => {
    expect(render('fallback')).toContain('The detailed verdict could not be written; showing aggregates only.')
    expect(NARRATIVE_FALLBACK_COPY).toBe('The detailed verdict could not be written; showing aggregates only.')
  })

  it('stays silent for every other status — a normal verdict carries no notice', () => {
    expect(render('ok')).toBe('')
    expect(render('')).toBe('')
  })

  it('marks the notice in warn while the words stay ink (R35)', () => {
    const html = render('fallback')
    expect(html).toContain('border-warn') // the rule, the annotation
    expect(html).toContain('text-warn') // the mark
    expect(html).toContain('text-body text-ink') // the sentence
  })
})
