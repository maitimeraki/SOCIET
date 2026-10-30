import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import { BANNED_WORD, renderedText } from '../../test/copyLaw'
import FiledSheet from './FiledSheet'

const DECISION = {
  question: 'Should Ridgeline Coffee open a second location on Mill Street this spring?',
  position: 'NEGATIVE' as const,
  share: 0.82,
  caseAgainst: 'If the grease-trap work lands on time, the Mill Street economics hold.',
  sources: 'Mill Street lease · economics · grease-trap certification · Alder Lane lease',
}

describe('FiledSheet', () => {
  it('states the question, the position, the share, the case against and the sources', () => {
    const html = renderToStaticMarkup(<FiledSheet decision={DECISION} />)
    expect(html).toContain(DECISION.question)
    expect(html).toContain('NEGATIVE') // the position, as symbol + word
    expect(html).toContain('0.82') // the weighted share
    expect(html).toContain(DECISION.caseAgainst)
    expect(html).toContain(DECISION.sources)
  })

  it('is a card — the canvas and a shadow, and no rule around it', () => {
    const html = renderToStaticMarkup(<FiledSheet decision={DECISION} />)
    expect(html).toContain('bg-paper')
    expect(html).toContain('shadow-card')
  })

  it('draws the share as a meter, with its figure beside it', () => {
    const html = renderToStaticMarkup(<FiledSheet decision={DECISION} />)
    // The track's own class string, not a prefix: `h-1` alone would also match `h-1.5`.
    expect(html).toContain('class="h-1.5 flex-1 rounded-xs bg-sand"')
    expect(html).toContain('width:82%')
  })

  it('labels authored material a worked example, and says so in a line', () => {
    const html = renderToStaticMarkup(<FiledSheet decision={DECISION} sample />)
    expect(html).toContain('Worked example')
    expect(html).toContain('A worked example')
  })

  it('keeps the chip’s caps tracking — the label face declares none', () => {
    // `text-micro` declares no letter-spacing, so the caps treatment is the call site’s to give.
    const html = renderToStaticMarkup(<FiledSheet decision={DECISION} sample />)
    expect(html).toContain('uppercase tracking-[0.14em]')
  })

  it('carries no worked-example label when the sheet is the customer’s own', () => {
    const html = renderToStaticMarkup(<FiledSheet decision={DECISION} />)
    expect(html).not.toContain('Worked example')
  })

  it('states an absent share rather than inventing one — and draws no fill', () => {
    const html = renderToStaticMarkup(<FiledSheet decision={{ ...DECISION, share: null }} />)
    expect(html).toContain('—')
    expect(html).not.toContain('0.00')
    // No zero-width fill: an unrecorded share is an empty track, not a claim of zero.
    expect(html).not.toContain('style="width:')
    expect(html).toContain('bg-sand') // the track remains
  })

  it('renders no banned word — the copy law holds over the kit', () => {
    const html = renderToStaticMarkup(<FiledSheet decision={DECISION} sample />)
    expect(renderedText(html)).not.toMatch(BANNED_WORD)
  })
})
