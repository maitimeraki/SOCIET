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

  it('tags a judgement point only when the line ends with the tag', () => {
    expect(reportBlocks('(judgement) is not a tag here, the line goes on')[0]).toMatchObject({ judgement: false })
    expect(reportBlocks('A point (judgement)')[0]).toMatchObject({ judgement: true })
  })

  it('adds nothing the markdown does not say', () => {
    expect(reportBlocks('')).toEqual([])
    expect(reportBlocks('Plain line.')).toEqual([{ kind: 'paragraph', text: 'Plain line.', judgement: false }])
  })
})

describe('inlineParts — bold spans and citation markers, in order', () => {
  it('splits text, bold and citation parts', () => {
    expect(inlineParts('A **strong** claim [2] here')).toEqual([
      { kind: 'text', text: 'A ' },
      { kind: 'bold', text: 'strong' },
      { kind: 'text', text: ' claim ' },
      { kind: 'source', n: '2', raw: '[2]' },
      { kind: 'text', text: ' here' },
    ])
  })

  it('reads only digit markers as citations', () => {
    expect(inlineParts('[a] and [x1]').every((part) => part.kind === 'text')).toBe(true)
  })
})
