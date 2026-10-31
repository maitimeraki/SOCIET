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

/** The first viewport ends where the lower bands begin — the facts strip is the first one below it. */
const FIRST_VIEWPORT_END = 'aria-label="What is true of the product"'

const firstViewport = () => {
  const end = html.indexOf(FIRST_VIEWPORT_END)
  if (end < 0) throw new Error('the lower bands no longer follow the first viewport')
  return html.slice(0, end)
}

const count = (haystack: string, needle: string) => haystack.split(needle).length - 1

/** The page's section bands, in document order — §7.1's alternating grounds. */
const bands = [...html.matchAll(/<(?:section|footer)[^>]*class="band ([^"]*)"/g)].map((match) => match[1])
const bandTones = bands.map((classes) => classes.split(' ')[0])

/** The FAQ's own details, sliced out so the nav's mobile disclosure cannot count as a question. */
const faq = html.slice(html.indexOf('Good questions.'), html.indexOf('Bring a question'))

describe('the marketing page', () => {
  it('names the feeling in the first line', () => {
    // R10 — the source carries the curly apostrophe; renderToStaticMarkup passes it through, so an
    // `&rsquo;` entity in the expectation could never match.
    expect(html).toContain('The decision you can’t look up.')
    expect(html).not.toContain('&rsquo;')
    expect(html).toContain('A panel of experts')
  })

  it('offers one action, and says what is free', () => {
    expect(html).toContain('Start your first decision')
    expect(html).toContain('Free to start')
    expect(html).not.toContain('Free to use')
    expect(html).not.toContain('Get started')
  })

  it('states what it does not do', () => {
    expect(html).toContain('What it does not do')
  })

  it('states the cost in the five places, and never claims a free product at every volume', () => {
    // R63 / DESIGN §7.9 — hero trust line, the facts strip, trust proof 04, the FAQ answer, the close.
    expect(count(html, 'Free to start · No card')).toBe(5)
    expect(html).not.toContain('No card, no tier')
    expect(html).not.toContain('What does it cost? Nothing')
  })
})

describe('the first viewport — the map, the feeling, the one action', () => {
  it('carries the map capture, and no answer capture', () => {
    expect(count(firstViewport(), 'data-capture="map"')).toBe(1)
    expect(count(html, 'data-capture="answer"')).toBe(0)
  })

  it('names the feeling in one h1, and no more', () => {
    expect(count(html, '<h1')).toBe(1)
    const h1 = renderedText(html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/)?.[1] ?? '')
    expect(h1).toBe('The decision you can’t look up.')
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

  it('keeps one evergreen object on the page — the hero action', () => {
    // The nav's Start free is a secondary control; the close's one action is mint on pine.
    expect(count(html, 'action-fill')).toBe(1)
  })

  it('labels the authored evidence a worked example', () => {
    expect(renderedText(html)).toContain('Worked example')
  })
})

describe('the twelve parts — in order, each on its own surface', () => {
  it('renders the section headings in document order', () => {
    // Read the real <h2>s in document order — a substring search would match one heading inside
    // another ("What it does" inside "What it does. What it does not do.").
    const headings = [...html.matchAll(/<h2[^>]*>([\s\S]*?)<\/h2>/g)].map((match) => renderedText(match[1]))
    expect(headings).toEqual([
      'The argument is the thing you’re missing.',
      'Four movements, always in the same order.',
      'Not a conversation. A filed decision.',
      'Four objects, every time.',
      'No borrowed credibility. The work is the proof.',
      'What it does. What it does not do.',
      'Where it earns its keep.',
      'Good questions.',
      'Bring a question you can’t look up.',
    ])
  })

  it('alternates bone and sand, and gives the pine close the only dark band', () => {
    expect(bands).toHaveLength(11)
    expect(bandTones).toEqual([
      'band--page',
      'band--band',
      'band--page',
      'band--band',
      'band--page',
      'band--band',
      'band--page',
      'band--band',
      'band--page',
      'band--dark',
      'band--page',
    ])
    expect(count(html, 'band--dark')).toBe(1)
  })

  it('opens with the ruled facts strip between the hero and the problem', () => {
    const facts = html.indexOf(FIRST_VIEWPORT_END)
    expect(facts).toBeGreaterThan(html.indexOf('A panel of experts'))
    expect(facts).toBeLessThan(html.indexOf('The argument is the thing you’re missing.'))
    const strip = html.slice(facts, html.indexOf('The argument is the thing you’re missing.', facts))
    expect(count(strip, 'rule-y')).toBe(1)
  })

  it('draws the FAQ as six native disclosures, one marker each', () => {
    expect(count(faq, '<details')).toBe(6)
    expect(count(faq, 'group-open:hidden')).toBe(6)
  })
})

describe('the nav — a 72px bar, not a floating card', () => {
  it('sits on one hairline under a bone bar', () => {
    const header = html.match(/<header[^>]*>/)?.[0] ?? ''
    expect(header).toContain('sticky')
    expect(header).toContain('border-b')
    expect(header).not.toContain('shadow-card')
    expect(header).not.toContain('rounded-lg')
  })

  it('links to the three sections it names', () => {
    expect(html).toContain('href="#how-it-works"')
    expect(html).toContain('href="#answer"')
    expect(html).toContain('href="#questions"')
  })

  it('links the pricing page from the footer, so it is not orphaned (§7.1)', () => {
    expect(html).toContain('href="/pricing"')
  })
})

describe('the contact and the target sizes', () => {
  it('uses the one deliverable address everywhere on the page', () => {
    expect(html).toContain('mailto:hello@societas.app')
    expect(html).not.toContain('societas.example')
  })

  it('gives the footer and nav links a 44px target', () => {
    const tags = [...html.matchAll(/<a\b[^>]*>/g)].map((match) => match[0])
    // The section and footer text links; the CTA buttons are sized by `buttonClasses`.
    const standalone = tags.filter((tag) => /href="(?:#|mailto:|\/pricing)/.test(tag))
    expect(standalone.length).toBeGreaterThan(4)
    for (const tag of standalone) expect(tag).toContain('min-h-11')
  })
})

describe('the kit — the vocabulary the page is built from', () => {
  it('names the four sides of the rule', () => {
    expect(ruleClasses('top')).toBe('rule-t')
    expect(ruleClasses('bottom')).toBe('rule-b')
    expect(ruleClasses('both')).toBe('rule-y')
    expect(ruleClasses('around')).toBe('divide-rule')
  })

  it('hands no hand-rolled hairline to a page container', () => {
    // §14.1's sweep pattern, `border-t border-hairline`, and its bare form: zero on this page.
    expect(count(html, 'border-t border-hairline')).toBe(0)
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
