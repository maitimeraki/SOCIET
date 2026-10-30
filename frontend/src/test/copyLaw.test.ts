import { describe, expect, it } from 'vitest'
import { BANNED_WORD, renderedText } from './copyLaw'

// The guard sees the text BETWEEN tags AND the four customer-visible attribute values. A prior bug
// replaced each whole tag, so a banned word in aria-label/title/placeholder/alt was invisible.
describe('renderedText — the guard reads what the customer reads', () => {
  const banned = (markup: string) => BANNED_WORD.test(renderedText(markup))

  it('catches a banned word in aria-label', () => {
    expect(banned('<button aria-label="remove this agent">x</button>')).toBe(true)
  })

  it('catches a banned word in title', () => {
    expect(banned('<span title="the graph view">x</span>')).toBe(true)
  })

  it('catches a banned word in placeholder', () => {
    expect(banned('<input placeholder="describe your job" />')).toBe(true)
  })

  it('catches a banned word in alt', () => {
    expect(banned('<img alt="a node diagram" />')).toBe(true)
  })

  it('reads the text content between tags too', () => {
    expect(banned('<p>The round closed.</p>')).toBe(true)
  })

  it('ignores identifiers — className="rounded-md" must not trip the round stem', () => {
    expect(banned('<div className="rounded-md bg-bone">ok</div>')).toBe(false)
  })

  it('ignores data-* identifiers', () => {
    expect(banned('<div data-node-id="n1" data-round="2">ok</div>')).toBe(false)
  })

  it('reads single-quoted attribute values', () => {
    expect(banned("<button aria-label='remove this agent'>x</button>")).toBe(true)
  })
})
