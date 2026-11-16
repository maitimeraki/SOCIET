import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo: the reader renders to static markup in Node. The drawer
// is closed at render, so the passage itself is fetched on a press and is not part of this suite.
import { renderToStaticMarkup } from 'react-dom/server'
import AnswerDocument from './AnswerDocument'
// §13 — the one copy-law guard, shared with every rendered-string test.
import { BANNED_TERMS, renderedText } from '../../test/copyLaw'

const MARKDOWN = [
  '# Should we expand into Europe?',
  '## Recommendation',
  'Position: POSITIVE, 83%, settled',
  'Expand, **cautiously**, into one market first.',
  '## Entry cost',
  'Point: Steel tariffs raise the cost [1] (from the documents)',
  'Point: One market first is the safer move (judgement)',
  'Result: Stage the entry [9] and hold the budget.',
].join('\n')

const SOURCES = { '1': { document: 'EU market study 2026', section: 'Tariffs' } }

const render = (markdown = MARKDOWN, sources = SOURCES) =>
  renderToStaticMarkup(<AnswerDocument runId="r1" markdown={markdown} sources={sources} />)

describe('the report reads as given — the client adds no section of its own', () => {
  it('renders the backend markdown, its title and its sections', () => {
    const html = render()
    expect(html).toContain('Should we expand into Europe?')
    expect(html).toContain('Position: POSITIVE, 83%, settled')
    expect(html).toContain('Entry cost')
  })

  it('adds no template heading, figure or fallback text', () => {
    const html = render()
    for (const added of ['The case against', 'Weighted confidence', 'On the record', 'Final stances', 'The passes', 'Who held which view']) {
      expect(html, added).not.toContain(added)
    }
  })

  it('renders bold spans as strong text, never as asterisks', () => {
    const html = render()
    expect(html).toContain('<strong class="font-semibold">cautiously</strong>')
    expect(html).not.toContain('**')
  })
})

describe('the citation markers', () => {
  it('turns a marker that names a source into a button whose name carries its visible number', () => {
    const html = render()
    expect(html).toMatch(/<button[^>]*aria-label="\[1\] open source"[^>]*>\[1\]<\/button>/)
  })

  it('leaves a marker with no source as plain text', () => {
    const html = render()
    expect(html).toContain('[9]')
    expect(html).not.toContain('aria-label="[9] open source"')
  })

  it('keeps the button for a citation inside bold', () => {
    const html = renderToStaticMarkup(
      <AnswerDocument runId="r1" markdown="Point: A **firm [1] claim** holds (from the documents)" sources={SOURCES} />,
    )
    expect(html).toMatch(/<strong[^>]*><button[^>]*>\[1\]<\/button><\/strong>/)
  })

  it('shows no drawer until a source is opened', () => {
    expect(render()).not.toContain('role="dialog"')
  })
})

describe('judgement is visually distinct; the tag stays legible', () => {
  it('marks the judgement point with a rule and keeps its tag in the text', () => {
    const html = render()
    expect(html.match(/border-l-2/g)).toHaveLength(1)
    expect(html).toContain('(judgement)')
    expect(html).toContain('(from the documents)')
  })
})

describe('copy law', () => {
  it('renders no banned word from the report it is given', () => {
    expect(renderedText(render())).not.toMatch(BANNED_TERMS)
  })
})
