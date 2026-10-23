import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import { BANNED_WORD, renderedText } from '../../test/copyLaw'
import Chip, { StateChip } from './Chip'

describe('Chip', () => {
  it('is a small bordered tag on the radius token, never a literal', () => {
    const html = renderToStaticMarkup(<Chip>finance</Chip>)
    expect(html).toContain('border')
    expect(html).toContain('rounded-xs')
    expect(html).not.toContain('rounded-[4px]')
  })

  it('takes its tone from the variant, not from the call site', () => {
    const neutral = renderToStaticMarkup(<Chip>finance</Chip>)
    const status = renderToStaticMarkup(<Chip tone="status">Complete</Chip>)
    const accent = renderToStaticMarkup(<Chip tone="accent">Live</Chip>)
    expect(neutral).not.toBe(status)
    expect(status).not.toBe(accent)
    expect(accent).toContain('text-accent')
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

  it('takes the accent while the run is live, and the status ink when it is not', () => {
    expect(renderToStaticMarkup(<StateChip state="running" />)).toContain('text-accent')
    expect(renderToStaticMarkup(<StateChip state="complete" />)).not.toContain('text-accent')
  })

  it('renders no banned word — the copy law holds over the kit', () => {
    const html = renderToStaticMarkup(<Chip tone="status">Complete</Chip>)
    expect(renderedText(html)).not.toMatch(BANNED_WORD)
  })
})
