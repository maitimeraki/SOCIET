import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): the reading view renders
// to static markup in Node, and the export is asserted on its own text. Both come from the one pure
// section builder, so "what is read and what leaves are the same document" is pinned, not assumed.
import { renderToStaticMarkup } from 'react-dom/server'
import type { VerdictView } from '../../run/selectors'
import { NARRATIVE_FALLBACK_COPY } from '../verdict/NarrativeFallbackNotice'
import { stanceWord } from '../ui/PositionMark'
import AnswerDocument, { answerSections, answerText, blockLines, sourceTitles } from './AnswerDocument'
import type { AnswerBlock, AnswerInput } from './AnswerDocument'
// §13 — the one copy-law guard, shared with every rendered-string test.
import { BANNED_TERMS, renderedText } from '../../test/copyLaw'

const SOURCES = ['Market research 2026', 'Finance brief']
const QUESTION = 'Should we expand into Europe?'

const view = (patch: Partial<VerdictView> = {}): VerdictView => ({
  stance: 'POSITIVE',
  confidence: 0.82,
  converged: true,
  summary: 'Aggregate reading: lean positive.',
  narrative: '## Summary\nExpand, with care.\n\n## Risks\nWatch the logistics.',
  narrativeStatus: 'ok',
  dissentingViews: [{ stance: 'NEGATIVE', view: 'Cash flow is too tight this year.' }],
  evidence: [{ entity: 'Nordic demand', claim: 'Growing at double digits.' }],
  clusters: [],
  finalStances: [
    { agent: 'Nordic Lead', stance: 'POSITIVE' },
    { agent: 'Baltic Lead', stance: 'NEGATIVE' },
  ],
  supporting: ['Nordic demand'],
  opposing: ['Steel tariffs'],
  warnings: ['Source coverage is thin for the Baltic market.'],
  ...patch,
})

const input = (patch: Partial<AnswerInput> = {}): AnswerInput => ({
  question: QUESTION,
  view: view(),
  sources: SOURCES,
  corpusMissing: false,
  ...patch,
})

const render = (patch: Partial<AnswerInput> = {}) => renderToStaticMarkup(<AnswerDocument runId="r1" {...input(patch)} />)

/** The strings a block carries that must survive into BOTH surfaces — derived from the block itself,
 *  never restated as literals, so a field rendered on one side and dropped on the other fails. */
const blockStrings = (block: AnswerBlock): string[] => {
  switch (block.kind) {
    case 'text':
      return [block.text]
    case 'listing':
      return block.items
    case 'stances':
      // The customer-facing word, not the enum — both surfaces must render the same word (§4.6).
      return block.rows.flatMap((row) => [row.name, stanceWord(row.stance)])
    case 'entities':
      return [...block.supporting, ...block.opposing]
    case 'warnings':
      return block.items
  }
}

describe('AnswerDocument — §8.5 the outcome, readable', () => {
  it('shows the answer, the confidence, the strongest opposing case, the sources and the warnings', () => {
    const html = render()
    expect(html).toContain(QUESTION) // the decision it answers
    expect(html).toContain('Expand, with care.') // the written answer
    expect(html).toContain('0.82') // the weighted confidence
    expect(html).toContain('Cash flow is too tight this year.') // the case against, in words
    expect(html).toContain('Market research 2026') // a source
    expect(html).toContain('Finance brief')
    expect(html).toContain('Source coverage is thin for the Baltic market.') // the warning
  })

  it('renders a stance as symbol and colour and word, never a hue alone (§6/§9)', () => {
    const html = render()
    expect(html).toContain('▲') // the stance symbol
    expect(html).toContain('--color-pos-light') // the symbol's hue, not the word's
    expect(html).toContain('>Positive<') // the word beside it, never the enum
  })

  it('carries no banned word, authored or exported (§13)', () => {
    expect(renderedText(render())).not.toMatch(BANNED_TERMS)
    expect(answerText(input())).not.toMatch(BANNED_TERMS)
    // The fallback branch carries its own authored copy (NARRATIVE_FALLBACK_COPY) — scan it too.
    const fallback = input({ view: view({ narrative: '', narrativeStatus: 'fallback' }) })
    expect(answerText(fallback)).toContain(NARRATIVE_FALLBACK_COPY)
    expect(answerText(fallback)).not.toMatch(BANNED_TERMS)
    expect(renderedText(render({ view: fallback.view }))).not.toMatch(BANNED_TERMS)
  })
})

describe('AnswerDocument — read and export are the same document', () => {
  it('serializes the very sections and blocks the reading view renders', () => {
    const read = render()
    const text = answerText(input())
    // Parity is checked against the builder's own output, never a restated list: every section the one
    // derivation produced is in both surfaces, and every block it produced is serialized (non-empty)
    // with each of its strings present on BOTH sides — so a block dropped from one side cannot pass.
    for (const section of answerSections(input())) {
      expect(read, section.heading).toContain(section.heading)
      expect(text, section.heading).toContain(`## ${section.heading}`)
      for (const block of section.blocks) {
        const lines = blockLines(block)
        expect(lines.length, `${section.heading} serializes at least one line`).toBeGreaterThan(0)
        for (const line of lines) expect(text, line).toContain(line)
        for (const value of blockStrings(block)) {
          expect(text, value).toContain(value)
          expect(read, value).toContain(value)
        }
      }
    }
  })

  it('sheet mode renders the filed sheet alone — no reading view, no export', () => {
    const html = renderToStaticMarkup(<AnswerDocument runId="r1" {...input()} variant="sheet" />)
    expect(html).toContain(QUESTION)
    expect(html).toContain('Positive') // the position, as symbol + word
    expect(html).toContain('0.82') // the weighted share
    expect(html).toContain('Cash flow is too tight this year.') // the case against
    expect(html).toContain('Market research 2026') // a source
    expect(html).not.toContain('Weighted confidence')
    expect(html).not.toContain('The answer') // no document sections
    expect(html).not.toContain('Export this verdict')
  })

  it('is self-contained: the answer names the decision it answers', () => {
    expect(answerText(input()).startsWith(`# ${QUESTION}`)).toBe(true)
  })
})

describe('AnswerDocument — honesty about what it does not have (D7)', () => {
  it('names the fallback the payload marks and never claims a written answer exists', () => {
    const fallback = view({ narrative: '', narrativeStatus: 'fallback' })
    const text = answerText(input({ view: fallback }))
    expect(text).toContain(NARRATIVE_FALLBACK_COPY) // says it is aggregates only
    expect(text).toContain('Aggregate reading: lean positive.') // the fallback summary stands
    expect(text).toContain('## The outcome') // not "The answer" — no written answer is claimed
    expect(text).not.toContain('## The answer')
    expect(render({ view: fallback })).toContain(NARRATIVE_FALLBACK_COPY)
  })

  it('states an absent source list rather than showing an empty one', () => {
    expect(answerText(input({ sources: [] }))).toContain('No sources were recorded')
  })

  it('says the material is gone when the corpus is missing, rather than omitting sources', () => {
    expect(answerText(input({ sources: [], corpusMissing: true }))).toContain('no longer available')
    expect(answerText(input({ corpusMissing: true }))).toContain('no longer available')
  })

  it('shows no warnings section when there are none', () => {
    expect(answerText(input({ view: view({ warnings: [] }) }))).not.toContain('## Warnings')
  })
})

describe('sourceTitles', () => {
  it('collects the distinct source titles a run reads from, in first-seen order', () => {
    const profile = (name: string, titles: string[]) => ({
      agent_id: name,
      identity: { name, archetype: 'analyst', communication_style: 'plain' },
      bio: '',
      detailed_perspective: '',
      stance: 'POSITIVE' as const,
      intensity: 0.5,
      confidence: 0.6,
      conviction: 0.6,
      cior: 0,
      domain_tags: [],
      communication_radius: 1,
      summary_provenance: titles.map((title, i) => ({ doc_id: `${name}-${i}`, title, chunk_id: 'c1' })),
      confidence_breakdown: { source_breadth: 1, node_density: 1, relationship_connectivity: 1 },
    })
    expect(sourceTitles([profile('a', ['First', 'Second']), profile('b', ['Second', 'Third'])])).toEqual([
      'First', 'Second', 'Third',
    ])
  })

  it('names nothing when no expert read from anything', () => {
    expect(sourceTitles([])).toEqual([])
  })
})
