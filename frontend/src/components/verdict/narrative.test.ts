import { describe, expect, it } from 'vitest'
import { splitSections } from './narrative'

describe('splitSections', () => {
  it('splits ## headings into sections with their body', () => {
    const md = '## Recommendation\nExpand, cautiously.\n\n## Reasoning\nSteel tariffs bite.'
    expect(splitSections(md)).toEqual([
      { heading: 'Recommendation', body: 'Expand, cautiously.' },
      { heading: 'Reasoning', body: 'Steel tariffs bite.' },
    ])
  })

  it('keeps text before the first heading as a heading-less preamble', () => {
    expect(splitSections('Intro line.\n## Reasoning\nBecause.')).toEqual([
      { heading: '', body: 'Intro line.' },
      { heading: 'Reasoning', body: 'Because.' },
    ])
  })

  it('treats markdown with no headings as one body-only section', () => {
    expect(splitSections('Just a summary paragraph.')).toEqual([
      { heading: '', body: 'Just a summary paragraph.' },
    ])
  })

  it('returns nothing for empty input', () => {
    expect(splitSections('')).toEqual([])
  })
})
