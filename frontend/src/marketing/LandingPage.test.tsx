import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import LandingPage from './LandingPage'
import * as copy from './copy'
import { footer, hero, meta } from './copy'

const html = renderToStaticMarkup(
  <MemoryRouter>
    <LandingPage />
  </MemoryRouter>,
)

/** The first viewport ends where the first lower section begins. */
const FIRST_VIEWPORT_END = 'id="in-the-open"'

const firstViewport = () => {
  const end = html.indexOf(FIRST_VIEWPORT_END)
  if (end < 0) throw new Error('the lower sections no longer follow the first viewport')
  return html.slice(0, end)
}

const count = (haystack: string, needle: string) => haystack.split(needle).length - 1

/** Static markup escapes entities; read the text a visitor actually reads. */
const decode = (markup: string) =>
  markup
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')

const text = (markup: string) => decode(markup.replace(/<[^>]*>/g, ' '))

/** §13 — whole-word and plural-tolerant, over values only (identifiers are exempt). */
const BANNED = [
  'agent', 'graph', 'node', 'edge', 'round', 'retrieval', 'ontology', 'model',
  'society', 'chunk', 'embedding', 'vector', 'llm', 'prompt', 'token', 'pipeline', 'job',
]
const BANNED_WORD = new RegExp(`\\b(?:${BANNED.join('|')})s?\\b`, 'i')

const stringsIn = (value: unknown): string[] => {
  if (typeof value === 'string') return [value]
  if (Array.isArray(value)) return value.flatMap(stringsIn)
  if (value && typeof value === 'object') return Object.values(value).flatMap(stringsIn)
  return []
}

describe('the first viewport — the feeling, the proof, the action', () => {
  it('names the product and offers sign in and start free', () => {
    const viewport = firstViewport()
    expect(text(viewport)).toContain(meta.wordmark)
    expect(text(viewport)).toContain(hero.signIn.label)
    expect(text(viewport)).toContain(hero.startFree.label)
    expect(viewport).toContain(`href="${hero.signIn.to}"`)
  })

  it('sets the fixed headline — the feeling, not a topic', () => {
    expect(hero.headline).toBe("A decision you can't look up.")
    expect(hero.headline).not.toMatch(/\?$/)
    const h1 = decode(html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/)?.[1] ?? '')
    expect(h1).toBe(hero.headline)
  })

  it('supports the headline with one line', () => {
    expect(text(firstViewport())).toContain(hero.support)
    expect(hero.support.match(/[.!?](\s|$)/g)).toHaveLength(1)
  })

  it('offers exactly one primary action, and it points at sign-up carrying a next', () => {
    const viewport = firstViewport()
    expect(count(viewport, 'data-action="primary"')).toBe(1)

    const actionTags = (viewport.match(/<a\b[^>]*>/g) ?? []).filter((tag) =>
      tag.includes('data-action="primary"'),
    )
    expect(actionTags).toHaveLength(1)
    // A real anchor: keyboard-reachable, and its target is sign-up landing on the first step —
    // `/new`, where the first document is added (not the existing-owner dashboard).
    expect(hero.primary.to).toBe('/auth/signup?next=/new')
    expect(actionTags[0]).toContain(`href="${hero.primary.to}"`)

    const after = viewport.slice(viewport.indexOf(actionTags[0]) + actionTags[0].length)
    expect(decode(after.slice(0, after.indexOf('</a>')))).toBe(hero.primary.label)
  })

  it('reserves the capture region without drawing a fake screenshot', () => {
    const viewport = firstViewport()
    expect(count(viewport, 'data-capture="region"')).toBe(1)
    expect(count(viewport, 'data-capture="map"')).toBe(1)
    expect(count(viewport, 'data-capture="verdict"')).toBe(1)
    expect(viewport).not.toContain('<img')
    expect(viewport).not.toContain('<svg')
  })
})

describe('the page below the first viewport', () => {
  it('renders every section heading in DSPEC §7.1 order, with a sane heading order', () => {
    const order = [
      'The decision, in the open',
      'How it works',
      'How it differs',
      'What this tool does — and does not',
      'The record',
      'Questions owners ask',
    ]
    // Read the real <h2>s in document order — a substring search would match one heading inside
    // another ("The record" inside "The recording").
    const headings = [...html.matchAll(/<h2[^>]*>([\s\S]*?)<\/h2>/g)].map((match) => decode(match[1]))
    expect(headings).toEqual(order)
    // The page has exactly one h1 — the first viewport's headline.
    expect(count(html, '<h1')).toBe(1)
  })

  it('shows no borrowed credibility and no certification claim', () => {
    // No logos, testimonials, case studies or certifications exist, so none may be implied.
    expect(html).not.toMatch(/SOC 2|ISO 27001/i)
    expect(html).not.toMatch(/certified|compliant/i)
    expect(html).not.toMatch(/trusted by/i)
  })

  it('fabricates no evidence anywhere on the page', () => {
    // No recording, capture, sample decision or benchmark figure stands in for proof.
    expect(html).not.toContain('<img')
    expect(html).not.toContain('<video')
    expect(html).not.toContain('<source')
    expect(html).not.toContain('.mp4')
    expect(html).not.toMatch(/\d+%/)
    expect(html).not.toContain('EU Trade Brief')
    expect(html).not.toContain('Market Sizing Workbook')
    expect(html).not.toContain('Data-Readiness Note')
    expect(html).not.toContain('0.82')
  })

  it('closes on the title block with the wordmark and the real actions', () => {
    expect(html).toContain(meta.wordmark)
    expect(html).toContain(footer.contact.label)
    expect(html).toContain(footer.contact.href)
    expect(html).toContain(footer.primary.label)
  })

  it('leaves no unresolved value in the markup', () => {
    expect(html).not.toContain('undefined')
    expect(html).not.toContain('NaN')
  })
})

describe('the copy law (§13)', () => {
  it('holds over every customer-visible string in the copy object', () => {
    for (const [key, value] of Object.entries(copy)) {
      for (const valueText of stringsIn(value)) {
        expect(valueText, `${key}: ${valueText}`).not.toMatch(BANNED_WORD)
      }
    }
  })

  it('holds over every rendered string on the page', () => {
    expect(text(html)).not.toMatch(BANNED_WORD)
  })

  it('the pattern itself is whole-word and plural-tolerant', () => {
    expect(BANNED_WORD.test('an agent here')).toBe(true)
    expect(BANNED_WORD.test('Agents')).toBe(true)
    expect(BANNED_WORD.test('bg-ground background ground')).toBe(false)
  })
})
