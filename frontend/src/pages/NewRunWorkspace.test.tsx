import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx). The page exports a pure
// view whose step is a plain prop (Ruling F17/F23), so each step renders to static markup in Node.
// The map host is the shell's now (see WorkspaceShell.test.tsx); this file asserts the page's own
// step rail and step surface.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { NewRunWorkspaceView, stepFromParam, type WorkspaceStep } from './NewRunWorkspace'
// §13: the visible step labels — the query value (`ingest`/`graph`/`society`) is an internal
// identifier and stays exempt; only these rendered words are governed. Read from the one label map
// so a widened map (R13) cannot drift from the rail the customer sees.
import { STEP_LABELS } from './workspaceSteps'
// §13 — the one copy-law guard, shared with every rendered-string test.
import { BANNED_TERMS, renderedText } from '../test/copyLaw'

const STEPS = ['ingest', 'graph', 'society'] as const

const renderStep = (step: WorkspaceStep, failed = false) =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={[`/new?step=${step}`]}>
      <NewRunWorkspaceView step={step} failed={failed} />
    </MemoryRouter>,
  )

/** Just the step rail's markup — the failure assertions must not trip on a body element (a running
 *  StageLine also pulses). */
const rail = (html: string) => html.slice(html.indexOf('<nav aria-label="Run stages"'), html.indexOf('</nav>') + 6)

/** The label of the stage the rail marks current — the first `text-label` word after `aria-current`. */
function currentLabel(html: string): string {
  const at = html.indexOf('aria-current="step"')
  if (at < 0) return ''
  return html.slice(at).match(/text-label uppercase">([^<]+)</)?.[1] ?? ''
}

describe('stepFromParam — the step is an internal identifier, defaulting to ingest (Ruling F22)', () => {
  it('defaults to ingest when the param is absent', () => {
    expect(stepFromParam(null)).toBe('ingest')
  })

  it('reads the graph step', () => {
    expect(stepFromParam('graph')).toBe('graph')
  })

  it('reads the society step', () => {
    expect(stepFromParam('society')).toBe('society')
  })

  it('falls back to ingest on an unknown value — a bad param never blanks the workspace', () => {
    expect(stepFromParam('wat')).toBe('ingest')
  })
})

describe('the step indicator advances with the step (§9.4)', () => {
  it.each(STEPS)('%s marks its own stage current', (step) => {
    expect(currentLabel(renderStep(step))).toBe(STEP_LABELS[step])
  })
})

describe('the rail keeps its literal step words', () => {
  // Pinned literally as well as against `STEP_LABELS`: widening the map (R13) must not reword the rail.
  it.each([
    ['ingest', 'Your material'],
    ['graph', 'The map'],
    ['society', 'Your question'],
  ] as const)('%s reads %s', (step, word) => {
    expect(currentLabel(renderStep(step))).toBe(word)
  })
})

describe('a failed step reads as failed in the rail, never as running (§9.4)', () => {
  // The old GraphPage rail carried a `failed` marker (XCircle in `text-danger`); when it moved into
  // the workspace the marker was lost, so a failure showed a *pulsing* dot beside the body's error —
  // an indicator that contradicts the body. The step state now carries the failure signal.
  it('carries the danger marker on the current step instead of the running pulse', () => {
    const bar = rail(renderStep('graph', true))
    expect(bar).toContain('text-danger')
    expect(bar).not.toContain('animate-pulse')
  })

  it('still pulses while the step is running — the failure flag is what flips it', () => {
    const bar = rail(renderStep('graph'))
    expect(bar).toContain('animate-pulse')
    expect(bar).not.toContain('text-danger')
  })
})

describe('each step renders its own activity into the work pane', () => {
  it('the ingest step renders the material surface', () => {
    expect(renderStep('ingest')).toContain('Build the corpus')
  })

  it('the graph step renders the map-building surface', () => {
    expect(renderStep('graph')).toContain('Grow the map')
  })

  it('the society step renders the question surface', () => {
    expect(renderStep('society')).toContain('Set the question')
  })

  it('does not render another step’s surface', () => {
    expect(renderStep('ingest')).not.toContain('Grow the map')
    expect(renderStep('graph')).not.toContain('Build the corpus')
  })
})

describe('the copy law (§13) holds on the workspace at every step', () => {
  // The shared, stem-tolerant pattern, matched against the RENDERED TEXT only (tags/attributes
  // stripped), so `bg-bone` can never trip `\bround\b`.
  it.each(STEPS)('%s renders no banned word', (step) => {
    expect(renderedText(renderStep(step))).not.toMatch(BANNED_TERMS)
  })
})
