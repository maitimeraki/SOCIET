/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import LandingPage from './LandingPage'
import * as copy from './copy'
import { captures, footer, hero, meta } from './copy'
// §13 — the one copy-law guard (list + stem-tolerant matcher), shared with every rendered-string test.
import { BANNED_WORD } from '../test/copyLaw'

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

  it('holds the first viewport to one real frame — the filed answer', () => {
    const viewport = firstViewport()
    expect(count(viewport, 'data-capture="region"')).toBe(1)
    expect(count(viewport, 'data-capture="answer"')).toBe(1)
    expect(count(viewport, 'data-capture="case"')).toBe(0)
    // F62: the hero carries the answer capture alone — the map is proof, not first-viewport decoration.
    expect(count(viewport, 'data-capture="map"')).toBe(0)
    // The frame is the real capture, not a drawn placeholder.
    expect(viewport).toContain(`src="${captures.answer.src}"`)
    expect(viewport).not.toContain(`src="${captures.opposingCase.src}"`)
    expect(viewport).not.toContain('<svg')
  })

  it('keeps the opposing case on the page, under the stage that files it', () => {
    expect(count(html, 'data-capture="case"')).toBe(1)
    const caseFrame = html.match(/<figure[^>]*data-capture="case"[\s\S]*?<\/figure>/)?.[0] ?? ''
    expect(caseFrame).toContain(`src="${captures.opposingCase.src}"`)
    expect(caseFrame).toContain(`alt="${captures.opposingCase.alt}"`)
    // It follows the stage whose claim it shows, and the workspace still ships below it.
    expect(html.indexOf('data-capture="case"')).toBeGreaterThan(html.indexOf('The answer, filed with its case'))
    expect(html.indexOf('data-capture="workspace"')).toBeGreaterThan(html.indexOf('data-capture="case"'))
  })

  it('ships the real map under stage 2, before the case and workspace frames', () => {
    expect(count(html, 'data-capture="map"')).toBe(1)
    const mapFrame = html.match(/<figure[^>]*data-capture="map"[\s\S]*?<\/figure>/)?.[0] ?? ''
    expect(mapFrame).toContain(`src="${captures.map.src}"`)
    expect(mapFrame).toContain(`alt="${captures.map.alt}"`)
    // It follows the stage whose claim it shows, and the filed answer still ships below it.
    expect(html.indexOf('data-capture="map"')).toBeGreaterThan(html.indexOf('The panel, arguing in passes'))
    expect(html.indexOf('data-capture="case"')).toBeGreaterThan(html.indexOf('data-capture="map"'))
    expect(html.indexOf('data-capture="workspace"')).toBeGreaterThan(html.indexOf('data-capture="map"'))
  })
})

describe('the shipped captures — real frames of the running product', () => {
  it('renders every capture with an alt, its own pixels and a /captures/ source', () => {
    for (const [name, capture] of Object.entries(captures)) {
      expect(capture.alt, name).not.toBe('')
      expect(capture.src, name).toMatch(/^\/captures\//)
      const tag = html.match(new RegExp(`<img[^>]*src="${capture.src}"[^>]*>`))?.[0]
      expect(tag, `${name} is not rendered`).toBeTruthy()
      expect(tag, name).toContain(`alt="${capture.alt}"`)
      expect(tag, name).toContain(`width="${capture.width}"`)
      expect(tag, name).toContain(`height="${capture.height}"`)
    }
  })

  it('declares the map at the capture file’s own pixels', () => {
    // vitest runs from `frontend/`, where the public tree is served from.
    const png = readFileSync(`${process.cwd()}/public/captures/map-material.png`)
    expect([png.readUInt32BE(16), png.readUInt32BE(20)]).toEqual([captures.map.width, captures.map.height])
  })

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
    // No recording, sample decision or benchmark figure stands in for proof. The only images are the
    // real captures, which the shipped-captures suite checks for alt, size and source.
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
