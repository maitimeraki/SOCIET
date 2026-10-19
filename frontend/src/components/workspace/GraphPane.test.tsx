import { describe, expect, it, vi } from 'vitest'
// No jsdom / no testing-library in this repo (see Workspace.test.tsx): the pane is split into a
// stateful wrapper and an exported pure VIEW whose layer set is a plain prop (Ruling F17), so every
// toggle state — and every map size — renders to static markup in Node. "Pressing a toggle filters
// the canvas without unmounting it" is not assertable without a DOM: it is satisfied by
// construction (the canvas is the pane's always-rendered child; the filter is a prop change on a
// canvas that is never torn down) and stated as such, never faked with a simulated click.
import { renderToStaticMarkup } from 'react-dom/server'
import Graph from 'graphology'
import { EXPERT_TYPE } from '../../graph/graphStore'
import type { GraphEdge, GraphNode } from '../../graph/graphStore'
import { ALL_LAYERS, LAYER_NAMES, visibleSlice, type LayerName } from '../../graph/layers'
import {
  MAX_ANIMATED_NODES,
  MAX_LABELLED_NODES,
  shouldAnimateLayout,
  showNodeLabels,
  syncGraph,
} from '../graph/GraphCanvas'
import { GraphPaneView, mapCounts } from './GraphPane'
import type { MapSummary, PaneState } from './Workspace'
// §13 — the one copy-law guard, shared with every rendered-string test.
import { BANNED_WORD, renderedText } from '../../test/copyLaw'

// No jsdom / no testing-library (see GraphCanvas.test.tsx): the graph stack binds WebGL at import
// under Node, so mock the one DOM-bound module the canvas pulls in.
vi.mock('@react-sigma/core', () => ({ SigmaContainer: () => null, useSigma: () => null }))

const MAP_ID = 'run-1'
const HOST_ID = `workspace-map-${MAP_ID}`

/** `count` material entries — the corpus layer, the only kind the extraction stream writes. */
const corpusNodes = (count: number): Record<string, GraphNode> =>
  Object.fromEntries(
    Array.from({ length: count }, (_, index) => [`n${index}`, { id: `n${index}`, label: `Entry ${index}`, type: 'Topic' }]),
  )

const summaryOf = (nodes: Record<string, GraphNode>, edges: Record<string, GraphEdge> = {}): MapSummary => ({
  counts: mapCounts(nodes, edges),
  busiest: [],
  step: 'The map',
})

const render = (summary: MapSummary, layers: ReadonlySet<LayerName> = ALL_LAYERS, state: PaneState = 'split') =>
  renderToStaticMarkup(
    <GraphPaneView
      mapId={MAP_ID}
      state={state}
      onStateChange={() => {}}
      summary={summary}
      layers={layers}
      onToggleLayer={() => {}}
    >
      <div data-map-canvas />
    </GraphPaneView>,
  )

/** The opening tag of the toggle button whose text is `label`, so an assertion lands on one button. */
function toggleTag(html: string, label: string): string {
  const close = html.indexOf(`${label}</button>`)
  if (close < 0) return ''
  const open = html.lastIndexOf('<button', close)
  return html.slice(open, html.indexOf('>', open) + 1)
}

/** The whole button whose text is `label`, mark and word together — for assertions about its icon. */
function toggleMarkup(html: string, label: string): string {
  const word = html.indexOf(`${label}</button>`)
  if (word < 0) return ''
  const open = html.lastIndexOf('<button', word)
  const close = html.indexOf('</button>', word)
  return html.slice(open, close + '</button>'.length)
}

/** The opening tag of the toggle group — so a `hidden` assertion lands on the group, not the map host. */
function groupTag(html: string): string {
  const at = html.indexOf('role="group"')
  if (at < 0) return ''
  const open = html.lastIndexOf('<div', at)
  return html.slice(open, html.indexOf('>', open) + 1)
}

describe('the layer toggles — §9.1, every layer is a real button (§12)', () => {
  it('draws one toggle per layer, plus All, inside a labelled group', () => {
    const html = render(summaryOf(corpusNodes(2)))
    expect(html).toContain('role="group"')
    for (const label of ['All', 'Corpus', 'Experts', 'Opinions', 'Connections']) {
      expect(html, label).toContain(`${label}</button>`)
      expect(toggleTag(html, label), label).toContain('<button')
      expect(toggleTag(html, label), label).toContain('aria-pressed=')
    }
  })

  it('draws a decorative icon per layer, never a typographic glyph', () => {
    const html = render(summaryOf(corpusNodes(2)))
    for (const label of ['Corpus', 'Experts', 'Opinions', 'Connections']) {
      const markup = toggleMarkup(html, label)
      expect(markup, label).toContain('<svg')
      expect(markup, label).toContain('aria-hidden="true"')
      expect(markup, label).toContain(`${label}</button>`)
    }
    expect(html).not.toMatch(/[⊕◉⊗]/)
    // The master toggle is words only — it has no kind of its own to mark.
    expect(toggleMarkup(html, 'All')).not.toContain('<svg')
  })

  it('opens with every layer on, so All reads as pressed', () => {
    const html = render(summaryOf(corpusNodes(2)))
    for (const label of ['All', 'Corpus', 'Experts', 'Opinions', 'Connections']) {
      expect(toggleTag(html, label), label).toContain('aria-pressed="true"')
    }
  })

  it('marks a hidden layer unpressed — a state a colour alone could not carry', () => {
    const html = render(summaryOf(corpusNodes(2)), new Set<LayerName>(['corpus']))
    expect(toggleTag(html, 'Opinions')).toContain('aria-pressed="false"')
    expect(toggleTag(html, 'Opinions')).toContain('line-through')
    expect(toggleTag(html, 'Corpus')).toContain('aria-pressed="true"')
  })

  it('is not pressed on All while any layer is hidden', () => {
    const html = render(summaryOf(corpusNodes(2)), new Set<LayerName>(['corpus', 'experts']))
    expect(toggleTag(html, 'All')).toContain('aria-pressed="false"')
  })

  it('hides the toggles with the map in minimised — no off-screen button stays in the tab order', () => {
    expect(groupTag(render(summaryOf(corpusNodes(2)), ALL_LAYERS, 'minimised'))).toMatch(/hidden=""/)
  })

  it('keeps the toggles reachable while the map is shown', () => {
    expect(groupTag(render(summaryOf(corpusNodes(2))))).toContain('<div')
    expect(groupTag(render(summaryOf(corpusNodes(2))))).not.toMatch(/hidden=""/)
  })
})

describe('the pane keeps the canvas mounted and hands it every visible entry (§9.3, D14)', () => {
  it('renders the map host in every state, including minimised', () => {
    for (const state of ['split', 'expanded', 'minimised'] as const) {
      expect(render(summaryOf(corpusNodes(2)), ALL_LAYERS, state), state).toContain(`id="${HOST_ID}"`)
    }
  })

  it('passes the whole store through while every layer is on — no hidden cap', () => {
    const nodes = corpusNodes(3)
    expect(visibleSlice(nodes, {}, ALL_LAYERS).nodes).toBe(nodes)
  })
})

describe('the canvas’s node budget still governs the wired map', () => {
  // The pane hands the canvas a slice of the store; these pin that a slice cannot smuggle the map
  // past the ceilings the canvas already enforces (label dropping at 400, a frozen layout at 1500).
  it('hands over every entry at the label ceiling — and the canvas sheds the labels', () => {
    const nodes = corpusNodes(MAX_LABELLED_NODES + 1)
    const graph = new Graph({ multi: true })

    const slice = visibleSlice(nodes, {}, ALL_LAYERS)
    syncGraph(graph, slice.nodes, slice.edges)

    expect(graph.order).toBe(MAX_LABELLED_NODES + 1)
    expect(showNodeLabels(graph.order)).toBe(false)
    expect(graph.getNodeAttribute('n0', 'label')).toBeUndefined()
  })

  it('freezes the layout past the animation ceiling', () => {
    expect(shouldAnimateLayout(MAX_ANIMATED_NODES)).toBe(true)
    expect(shouldAnimateLayout(MAX_ANIMATED_NODES + 1)).toBe(false)
  })

  it('still carries a whole visible slice into the graph at the animation ceiling', () => {
    const nodes = corpusNodes(MAX_ANIMATED_NODES + 1)
    const graph = new Graph({ multi: true })

    const slice = visibleSlice(nodes, {}, ALL_LAYERS)
    syncGraph(graph, slice.nodes, slice.edges)

    expect(graph.order).toBe(MAX_ANIMATED_NODES + 1)
  })
})

describe('the text alternative stays truthful as the map grows (§9.4, §12)', () => {
  it('counts the entries by kind and the connections, never one total', () => {
    const nodes: Record<string, GraphNode> = {
      'ds-1:steel tariffs': { id: 'ds-1:steel tariffs', label: 'steel tariffs', type: 'Topic' },
      'ds-1:D. Weber': { id: 'ds-1:D. Weber', label: 'D. Weber', type: EXPERT_TYPE },
      'ds-1:qh:1:D. Weber': { id: 'ds-1:qh:1:D. Weber', label: 'D. Weber · pass 1', type: 'Opinion' },
    }
    const edges: Record<string, GraphEdge> = {
      'ds-1:D. Weber|ds-1:qh:1:D. Weber|STATED': { source: 'ds-1:D. Weber', target: 'ds-1:qh:1:D. Weber', label: 'STATED' },
    }

    expect(mapCounts(nodes, edges)).toEqual({ entries: 1, experts: 1, opinions: 1, connections: 1 })
  })

  it('reads out every kind in the pane', () => {
    const html = render({
      counts: { entries: 12, experts: 4, opinions: 7, connections: 9 },
      busiest: ['Nordic capacity'],
      step: 'The map',
    })

    expect(html).toContain('12 entries')
    expect(html).toContain('4 experts')
    expect(html).toContain('7 opinions')
    expect(html).toContain('9 connections')
  })

  it('grows with the map, across the label ceiling', () => {
    expect(render(summaryOf(corpusNodes(MAX_LABELLED_NODES)))).toContain(`${MAX_LABELLED_NODES} entries`)
    expect(render(summaryOf(corpusNodes(MAX_LABELLED_NODES + 1)))).toContain(`${MAX_LABELLED_NODES + 1} entries`)
    expect(render(summaryOf(corpusNodes(MAX_ANIMATED_NODES + 1)))).toContain(`${MAX_ANIMATED_NODES + 1} entries`)
  })
})

describe('the copy law (§13) governs the pane’s own strings, toggles included', () => {
  it('renders no banned word in any state', () => {
    for (const state of ['split', 'expanded', 'minimised'] as const) {
      expect(renderedText(render(summaryOf(corpusNodes(2)), ALL_LAYERS, state)), state).not.toMatch(BANNED_WORD)
    }
  })

  it('names every layer without a banned word', () => {
    expect(LAYER_NAMES.join(' ')).not.toMatch(BANNED_WORD)
  })
})
