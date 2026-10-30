import { afterEach, describe, expect, it, vi } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): the shell renders to
// static markup in Node. The map host, its identity across pane states and the corpus-missing
// overlay are the shell's now, so their assertions live here — the pages render only their work.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import WorkspaceShell from './WorkspaceShell'
import { WorkspaceView, type MapSummary, type PaneState } from '../workspace/Workspace'
import { useRunStore } from '../../run/runStore'
// §13 — the one copy-law guard, shared with every rendered-string test.
import { BANNED_TERMS, renderedText } from '../../test/copyLaw'

// No jsdom / no testing-library (see GraphCanvas.test.tsx): the graph stack binds WebGL at import
// under Node, so mock the one DOM-bound module the shell pulls in through `GraphCanvas`.
vi.mock('@react-sigma/core', () => ({ SigmaContainer: () => null, useSigma: () => null }))

const work = <p>the work region</p>

const renderShell = (path: string) =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<WorkspaceShell />}>
          <Route path="/new" element={work} />
          <Route path="/runs/:runId" element={work} />
          <Route path="/runs/:runId/:tab" element={work} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )

const SUMMARY: MapSummary = {
  counts: { entries: 0, experts: 0, opinions: 0, connections: 0 },
  busiest: [],
  step: 'The map',
}

const renderPanes = (state: PaneState) =>
  renderToStaticMarkup(
    <WorkspaceView
      mapId="run-1"
      state={state}
      onStateChange={() => {}}
      map={<div data-map-canvas />}
      work={work}
      summary={SUMMARY}
    />,
  )

/** The opening tag of the first element whose markup contains `marker`. */
function tagAround(html: string, marker: string): string {
  const at = html.indexOf(marker)
  if (at < 0) return ''
  return html.slice(html.lastIndexOf('<', at), html.indexOf('>', at) + 1)
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('the workspace is the whole screen — no app rail, one map host', () => {
  it('renders no app rail, one map host, the work region and the way out', () => {
    const html = renderShell('/new')
    expect(html).not.toContain('aria-label="Sections"')
    expect(html).toContain('id="workspace-map-new"')
    expect(html.match(/id="workspace-map-/g)).toHaveLength(1)
    expect(html).toContain('the work region')
    expect(html).toContain('Exit')
  })

  it('renders the run map host for a run', () => {
    const html = renderShell('/runs/run-1/floor')
    expect(html).toContain('id="workspace-map-run-1"')
    expect(html.match(/id="workspace-map-/g)).toHaveLength(1)
    expect(html).toContain('the work region')
  })
})

describe('the run map keeps the height wrapper the canvas needs (D14)', () => {
  it('wraps the canvas in a growing flex child of the map host', () => {
    const html = renderShell('/runs/run-1/floor')
    const host = html.slice(html.indexOf('id="workspace-map-run-1"'))
    expect(host).toContain('relative flex min-h-0 flex-1 flex-col')
  })
})

describe('the run map says when its material is gone (§8.5)', () => {
  it('renders the corpus-missing status over the map', () => {
    // zustand's server snapshot is the captured initial state (v5), so the flag is flipped on that
    // object for the render and restored after — the shell's overlay is what is under test.
    const initial = useRunStore.getInitialState()
    const previous = initial.corpusMissing
    initial.corpusMissing = true
    try {
      const html = renderShell('/runs/run-1/floor')
      expect(html).toContain('role="status"')
      expect(html).toContain('The material behind this decision is no longer available.')
    } finally {
      initial.corpusMissing = previous
    }
  })
})

describe('the map host never unmounts across the pane states (§9.3, Ruling F17)', () => {
  it('keeps the host id byte-identical in split, expanded and minimised', () => {
    const ids = (['split', 'expanded', 'minimised'] as const).map((state) =>
      tagAround(renderPanes(state), 'id="workspace-map-run-1"').match(/id="[^"]+"/)?.[0],
    )
    expect(ids).toEqual([
      'id="workspace-map-run-1"',
      'id="workspace-map-run-1"',
      'id="workspace-map-run-1"',
    ])
  })

  it('keeps the work and the map on one seam radius (§14.4)', () => {
    const html = renderPanes('split')
    expect(tagAround(html, 'aria-label="The work"')).toContain('rounded-lg')
    expect(tagAround(html, 'aria-label="The map"')).toContain('rounded-lg')
    expect(tagAround(html, 'aria-label="The map"')).not.toContain('rounded-md')
  })
})

describe('the copy law (§13) holds on the shell', () => {
  it.each(['/new', '/runs/run-1/floor'])('%s renders no banned word', (path) => {
    expect(renderedText(renderShell(path))).not.toMatch(BANNED_TERMS)
  })
})
