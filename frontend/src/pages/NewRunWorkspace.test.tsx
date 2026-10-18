import { describe, expect, it, vi } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx). The workspace host is
// split into a stateful wrapper and an exported pure view whose pane state AND step are plain props
// (Ruling F17/F23), so each step renders to static markup in Node. "The step indicator advances
// without the map remounting" is asserted here as markup: the map host id is byte-identical across
// all three steps, and the rail marks the current step. A real DOM transition is not assertable
// without jsdom and is stated as a construction claim in the task report, never faked.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { NewRunWorkspaceView, stepFromParam, type WorkspaceStep } from './NewRunWorkspace'
import type { MapSummary, PaneState } from '../components/workspace/Workspace'

// No jsdom / no testing-library (see GraphCanvas.test.tsx): the graph stack binds WebGL at import
// under Node, so mock the one DOM-bound module the workspace page pulls in through `GraphCanvas`.
vi.mock('@react-sigma/core', () => ({ SigmaContainer: () => null, useSigma: () => null }))

const MAP_ID = 'new'
const HOST_ID = `workspace-map-${MAP_ID}`
const STEPS = ['ingest', 'graph', 'society'] as const
// §13: the visible step labels — the query value (`ingest`/`graph`/`society`) is an internal
// identifier and stays exempt; only these rendered words are governed.
const STEP_LABEL: Record<WorkspaceStep, string> = {
  ingest: 'Your material',
  graph: 'The map',
  society: 'Your question',
}

const SUMMARY: MapSummary = {
  counts: { entries: 0, experts: 0, opinions: 0, connections: 0 },
  busiest: [],
  step: '',
}

const renderStep = (step: WorkspaceStep, state: PaneState = 'split', failed = false) =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={[`/new?step=${step}`]}>
      <NewRunWorkspaceView
        step={step}
        mapId={MAP_ID}
        state={state}
        onStateChange={() => {}}
        map={<div data-map-canvas />}
        summary={SUMMARY}
        failed={failed}
      />
    </MemoryRouter>,
  )

/** The opening tag of the first element whose markup contains `marker`. */
function tagAround(html: string, marker: string): string {
  const at = html.indexOf(marker)
  if (at < 0) return ''
  return html.slice(html.lastIndexOf('<', at), html.indexOf('>', at) + 1)
}

const hostId = (html: string) => tagAround(html, `id="${HOST_ID}"`).match(/id="[^"]+"/)?.[0]

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

describe('one workspace, three steps — the map pane never unmounts (Ruling F22/F23, §9.3)', () => {
  it('renders the map host at every step', () => {
    for (const step of STEPS) expect(renderStep(step), step).toContain(`id="${HOST_ID}"`)
  })

  it('keeps the map host identity byte-identical across all three steps', () => {
    const ids = STEPS.map((step) => hostId(renderStep(step)))
    expect(ids).toEqual([`id="${HOST_ID}"`, `id="${HOST_ID}"`, `id="${HOST_ID}"`])
  })

  it('keeps the map host visible (no `hidden`) on the steps where the map is the point', () => {
    expect(hostId(renderStep('graph'))).not.toMatch(/ hidden=""/)
    expect(hostId(renderStep('society'))).not.toMatch(/ hidden=""/)
  })
})

describe('the step indicator advances with the step (§9.4)', () => {
  it.each(STEPS)('%s marks its own stage current', (step) => {
    expect(currentLabel(renderStep(step))).toBe(STEP_LABEL[step])
  })
})

describe('a failed step reads as failed in the rail, never as running (§9.4)', () => {
  // The old GraphPage rail carried a `failed` marker (XCircle in `text-danger`); when it moved into
  // the workspace the marker was lost, so a failure showed a *pulsing* dot beside the body's error —
  // an indicator that contradicts the body. The step state now carries the failure signal.
  it('carries the danger marker on the current step instead of the running pulse', () => {
    const bar = rail(renderStep('graph', 'split', true))
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
  // The whole-word, plural-tolerant pattern routes.test.tsx pins, matched against the RENDERED TEXT
  // only (tags/attributes stripped), so `bg-ground` can never trip `\bround\b`.
  const BANNED =
    /\b(?:agents?|graphs?|nodes?|edges?|rounds?|retrieval|ontolog(?:y|ies)|models?|societ(?:y|ies)|chunks?|embeddings?|vectors?|llms?|prompts?|tokens?|pipelines?|jobs?)\b/i
  const text = (html: string) => html.replace(/<[^>]*>/g, ' ')

  it.each(STEPS)('%s renders no banned word', (step) => {
    expect(text(renderStep(step))).not.toMatch(BANNED)
  })
})
