import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): the reading view renders
// to static markup in Node, and the export is asserted on its own text. Both come from the one pure
// section builder, so "what is read and what leaves are the same document" is pinned, not assumed.
import { renderToStaticMarkup } from 'react-dom/server'
import type { VerdictView } from '../../run/selectors'
import { NARRATIVE_FALLBACK_COPY } from '../verdict/NarrativeFallbackNotice'
import AnswerDocument, { answerSections, answerText, sourceTitles } from './AnswerDocument'
import type { AnswerInput } from './AnswerDocument'

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

/** The copy law (§13), matched on rendered text only: tags are stripped so a class never trips it. */
const BANNED = [
  'agent', 'graph', 'node', 'edge', 'round', 'retrieval', 'ontology', 'model',
  'society', 'chunk', 'embedding', 'vector', 'llm', 'prompt', 'token', 'pipeline', 'job',
]
const BANNED_WORD = new RegExp(`\\b(?:${BANNED.join('|')})s?\\b`, 'i')
const renderedText = (html: string) => html.replace(/<[^>]*>/g, ' ')

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
    expect(html).toContain('<svg') // the stance glyph
    expect(html).toContain('--color-pos-light') // the symbol's hue, not the word's
    expect(html).toContain('>POSITIVE<') // the word beside it
  })

  it('carries no banned word, authored or exported (§13)', () => {
    expect(renderedText(render())).not.toMatch(BANNED_WORD)
    expect(answerText(input())).not.toMatch(BANNED_WORD)
  })
})

describe('AnswerDocument — read and export are the same document', () => {
  it('serializes the very sections the reading view renders', () => {
    const read = render()
    const text = answerText(input())
    // Parity is checked against the builder's own output, not a second hardcoded list: every heading
    // the one derivation produced is in the page and in the file, so a drifted list cannot pass.
    for (const section of answerSections(input())) {
      expect(read, section.heading).toContain(section.heading)
      expect(text, section.heading).toContain(`## ${section.heading}`)
    }
    for (const value of [
      'Expand, with care.', '0.82', 'Cash flow is too tight this year.', 'Nordic demand', 'Market research 2026',
      'Source coverage is thin for the Baltic market.',
    ]) {
      expect(read, value).toContain(value)
      expect(text, value).toContain(value)
    }
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
