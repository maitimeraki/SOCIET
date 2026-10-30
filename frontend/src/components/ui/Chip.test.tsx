import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import { BANNED_TERMS, renderedText } from '../../test/copyLaw'
import Chip, { StateChip } from './Chip'

describe('Chip', () => {
  it('is a 24px mono caps tag on the radius token, never a literal', () => {
    const html = renderToStaticMarkup(<Chip>finance</Chip>)
    expect(html).toContain('h-6')
    expect(html).toContain('rounded-xs')
    expect(html).toContain('font-mono')
    expect(html).toContain('uppercase')
    expect(html).not.toContain('rounded-[4px]')
  })

  it('takes its tone from the variant, not from the call site', () => {
    const neutral = renderToStaticMarkup(<Chip>finance</Chip>)
    const verified = renderToStaticMarkup(<Chip tone="verified">Complete</Chip>)
    const danger = renderToStaticMarkup(<Chip tone="danger">Failed</Chip>)
    expect(neutral).not.toBe(verified)
    expect(verified).not.toBe(danger)
    expect(verified).toContain('text-ok')
    expect(danger).toContain('border-rule')
  })

  it('carries an icon beside the word when it is given one', () => {
    const html = renderToStaticMarkup(<Chip icon={<span data-icon="x" />}>Queued</Chip>)
    expect(html).toContain('data-icon="x"')
  })
})

describe('StateChip', () => {
  it('names the run’s state in words', () => {
    for (const [state, word] of [
      ['queued', 'Queued'],
      ['running', 'Deliberating'],
      ['complete', 'Complete'],
      ['converged', 'Converged'],
      ['failed', 'Failed'],
      ['interrupted', 'Interrupted'],
    ] as const) {
      expect(renderToStaticMarkup(<StateChip state={state} />)).toContain(word)
    }
  })

  it('turns the live mark and settles it when the run is no longer live', () => {
    expect(renderToStaticMarkup(<StateChip state="running" />)).toContain('animate-spin')
    expect(renderToStaticMarkup(<StateChip state="running" />)).toContain('text-warn')
    expect(renderToStaticMarkup(<StateChip state="complete" />)).not.toContain('animate-spin')
    expect(renderToStaticMarkup(<StateChip state="complete" />)).toContain('text-ok')
  })

  it('renders no banned word — the copy law holds over the kit', () => {
    const html = renderToStaticMarkup(<Chip tone="verified">Complete</Chip>)
    expect(renderedText(html)).not.toMatch(BANNED_TERMS)
  })
})
