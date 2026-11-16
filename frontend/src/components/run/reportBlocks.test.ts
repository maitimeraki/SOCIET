import { describe, expect, it } from 'vitest'
import { inlineParts, reportBlocks } from './reportBlocks'

const MARKDOWN = [
  '# Expand into Europe?',
  '## Recommendation',
  'Position: POSITIVE, 83%, settled',
  '- Stage the entry',
  '- Hold the budget',
  'Point: Tariffs raise the cost [1] (from the documents)',
  'Point: One market first is safer (judgement)',
].join('\n')

describe('reportBlocks — the report read as its own structure, never re-authored', () => {
  it('reads the title, the sections, the points and the lists in order', () => {
    expect(reportBlocks(MARKDOWN)).toEqual([
      { kind: 'title', text: 'Expand into Europe?' },
      { kind: 'heading', text: 'Recommendation' },
      { kind: 'paragraph', text: 'Position: POSITIVE, 83%, settled', judgement: false },
      { kind: 'list', items: ['Stage the entry', 'Hold the budget'] },
      { kind: 'paragraph', text: 'Point: Tariffs raise the cost [1] (from the documents)', judgement: false },
      { kind: 'paragraph', text: 'Point: One market first is safer (judgement)', judgement: true },
    ])
  })

  it('styles the judgement tag anywhere in a Point line, not only at its end', () => {
    expect(reportBlocks('Point: A claim (judgement) and more text')[0]).toMatchObject({ judgement: true })
  })

  it('reads the tag only on a Point line, so a Result line is never styled as a judgement', () => {
    expect(reportBlocks('Result: Stage it (judgement)')[0]).toMatchObject({ judgement: false })
  })

  it('adds nothing the markdown does not say', () => {
    expect(reportBlocks('')).toEqual([])
    expect(reportBlocks('Plain line.')).toEqual([{ kind: 'paragraph', text: 'Plain line.', judgement: false }])
  })
})

describe('inlineParts — bold spans and citation markers, in order', () => {
  it('splits text and citations, none of them bold', () => {
    expect(inlineParts('A claim [2] here')).toEqual([
      { kind: 'text', text: 'A claim ', strong: false },
      { kind: 'source', n: '2', raw: '[2]', strong: false },
      { kind: 'text', text: ' here', strong: false },
    ])
  })

  it('keeps a citation inside bold as a citation, marked bold', () => {
    expect(inlineParts('A **strong [1] claim** here')).toEqual([
      { kind: 'text', text: 'A ', strong: false },
      { kind: 'text', text: 'strong ', strong: true },
      { kind: 'source', n: '1', raw: '[1]', strong: true },
      { kind: 'text', text: ' claim', strong: true },
      { kind: 'text', text: ' here', strong: false },
    ])
  })

  it('reads only digit markers as citations', () => {
    expect(inlineParts('[a] and [x1]').every((part) => part.kind === 'text')).toBe(true)
  })
})
