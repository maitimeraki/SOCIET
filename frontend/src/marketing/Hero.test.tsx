import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { ruleClasses } from '../components/ui/Rule'
// §13 — the one copy-law guard (list + stem-tolerant matcher), shared with every rendered-string test.
import { BANNED_TERMS, renderedText } from '../test/copyLaw'
import Hero from './Hero'

const html = renderToStaticMarkup(
  <MemoryRouter>
    <Hero />
  </MemoryRouter>,
)

/** The first viewport ends where the lower bands begin — the facts band is the first one below it. */
const FIRST_VIEWPORT_END = 'aria-label="What is true of the product"'

const firstViewport = () => {
  const end = html.indexOf(FIRST_VIEWPORT_END)
  if (end < 0) throw new Error('the lower bands no longer follow the first viewport')
  return html.slice(0, end)
}

const count = (haystack: string, needle: string) => haystack.split(needle).length - 1

/** The page's bands, in document order — the twelve parts of §13.3, each on its own surface. */
const bands = [...html.matchAll(/<(?:section|footer)[^>]*class="band ([^"]*)"/g)].map((match) => match[1])
const bandTones = bands.map((classes) => classes.split(' ')[0])

describe('the first viewport — the map, the feeling, the one action', () => {
  it('carries the map capture, and not the answer capture', () => {
    // D3: the hero's frame is the map. The filed answer's capture lives further down the page.
    expect(count(firstViewport(), 'data-capture="map"')).toBe(1)
    expect(count(firstViewport(), 'data-capture="answer"')).toBe(0)
    expect(count(html, 'data-capture="answer"')).toBe(1)
  })

  it('names the feeling in one h1, and no more', () => {
    expect(count(html, '<h1')).toBe(1)
    const h1 = renderedText(html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/)?.[1] ?? '')
    expect(h1).toBe('A decision you can’t look up.')
  })

  it('offers exactly one primary action, and it points at sign-up carrying a next', () => {
    const viewport = firstViewport()
    expect(count(viewport, 'data-action="primary"')).toBe(1)

    const actionTags = (viewport.match(/<a\b[^>]*>/g) ?? []).filter((tag) =>
      tag.includes('data-action="primary"'),
    )
    expect(actionTags).toHaveLength(1)
    // A real anchor: keyboard-reachable, and its target is sign-up landing on the first step —
    // `/new`, where the first document is added.
    expect(actionTags[0]).toContain('href="/auth/signup?next=/new"')
  })

  it('labels the authored panel turns a worked example', () => {
    expect(renderedText(html)).toContain('Worked example')
  })
})

describe('the twelve parts — in order, each on its own surface', () => {
  it('renders the section headings in document order', () => {
    // Read the real <h2>s in document order — a substring search would match one heading inside
    // another ("What this tool does" inside "What this tool does — and does not").
    const headings = [...html.matchAll(/<h2[^>]*>([\s\S]*?)<\/h2>/g)].map((match) => renderedText(match[1]))
    expect(headings).toEqual([
      'The argument is the thing you’re missing.',
      'How it works',
      'What you get back',
      'Not a conversation. A filed decision.',
      'Where it earns its keep',
      'What this tool does — and does not',
      'The answer is a document you can open again.',
      'Good questions.',
      'Bring a question you can’t look up.',
    ])
  })

  it('lays the twelve bands out in order', () => {
    expect(bands).toHaveLength(12)
    expect(bandTones).toEqual([
      'band--page',
      'band--band',
      'band--warm',
      'band--sky',
      'band--plum',
      'band--band',
      'band--page',
      'band--band',
      'band--dark',
      'band--page',
      'band--plum',
      'band--band',
    ])
  })

  it('tightens three of them, and never gives two neighbours the same surface', () => {
    expect(count(html, 'band--dense')).toBe(3)
    for (let index = 1; index < bandTones.length; index += 1) {
      expect(bandTones[index], `bands ${index - 1} and ${index} share a surface`).not.toBe(bandTones[index - 1])
    }
  })
})

describe('the kit — the vocabulary the page is built from', () => {
  it('names the four sides of the rule', () => {
    expect(ruleClasses('top')).toBe('rule-t')
    expect(ruleClasses('bottom')).toBe('rule-b')
    expect(ruleClasses('both')).toBe('rule-y')
    expect(ruleClasses('around')).toBe('divide-rule')
  })

  it('takes every one of the page’s top rules from the kit', () => {
    // Eight call sites; three of them map over a list — the 3 facts, the 3 lines and the 4 steps —
    // so the page renders fifteen hairlines there, and one fewer would mean a site went
    // hand-rolled. The page's own FiledSheet drew three of those rules; the kit's FiledSheet
    // draws four, and the panel's four turns draw the rule in its dark tone — the same class,
    // on the map's own hairline. The ten FAQ Disclosures now open on the kit's own top rule.
    // 15 − 3 + 4 + 4 + 10 = 30.
    expect(count(html, 'rule-t')).toBe(30)
  })

  it('takes the panel’s hairlines from the kit in the map’s own rule', () => {
    // The noise panel is a dark surface outside the dark band, so its rows name the dark tone.
    expect(count(html, 'rule-dark')).toBe(4)
  })

  it('takes every one of the page’s divided lists from the kit', () => {
    expect(count(html, 'divide-rule')).toBe(2)
  })

  it('hands no hand-rolled top hairline to a page container', () => {
    // §14.1’s sweep pattern, `border-t border-hairline`: zero on this page.
    expect(count(html, 'border-t border-hairline')).toBe(0)
  })

  it('draws every FAQ separator with the kit’s own top rule', () => {
    // The Disclosure opens on the kit's top rule; the page draws no hand-rolled separator.
    expect(count(html, '<details')).toBe(10)
    expect(count(html, 'rule-b')).toBe(0)
    expect(count(html, 'border-hairline')).toBe(0)
  })
})

describe('the shipped captures — real frames of the running product', () => {
  it('gives every image on the page a non-empty alt, a size and a /captures/ source', () => {
    const tags = html.match(/<img\b[^>]*>/g) ?? []
    expect(tags.length).toBeGreaterThan(0)
    for (const tag of tags) {
      expect(tag).toMatch(/\balt="[^"]+"/)
      expect(tag).toMatch(/\bwidth="\d+"/)
      expect(tag).toMatch(/\bheight="\d+"/)
      expect(tag).toMatch(/\bsrc="\/captures\/[^"]+"/)
    }
  })
})

describe('the copy law (§13)', () => {
  it('holds over every rendered string on the page', () => {
    expect(renderedText(html)).not.toMatch(BANNED_TERMS)
  })

  it('leaves no unresolved value in the rendered text', () => {
    expect(renderedText(html)).not.toContain('undefined')
    expect(renderedText(html)).not.toContain('NaN')
  })
})
