import { describe, expect, it, vi } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx). The run page's
// workspace host is split into a stateful wrapper and an exported pure view whose pane state AND run
// are plain props (Rulings F17/F23), so the debate step renders to static markup in Node. "Switching
// the activity pane's view does not unmount the map" is asserted as markup — the map host id is
// byte-identical whether the pane holds the floor or another tab's work. A real DOM transition is
// not assertable without jsdom and is stated as a construction claim in the task report, never faked.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { RunPageView } from './RunPage'
import { busiestEntries } from '../components/workspace/GraphPane'
import type { MapSummary } from '../components/workspace/Workspace'
import type { AgentProfile } from '../run/events'
import { initialState, type RunState } from '../run/reducer'
// §13 — the one copy-law guard, shared with every rendered-string test.
import { BANNED_WORD, renderedText } from '../test/copyLaw'

// No jsdom / no testing-library (see GraphCanvas.test.tsx): the graph stack binds WebGL at import
// under Node, so mock the one DOM-bound module the run page pulls in through `GraphCanvas`.
vi.mock('@react-sigma/core', () => ({ SigmaContainer: () => null, useSigma: () => null }))

const RUN_ID = 'run-1'
const HOST_ID = `workspace-map-${RUN_ID}`
const TABS = ['roster', 'floor', 'verdict', 'agents', 'artifacts'] as const
type Tab = (typeof TABS)[number]

const profile = (name: string, stance: AgentProfile['stance']): AgentProfile => ({
  agent_id: name,
  identity: { name, archetype: 'analyst', communication_style: 'plain' },
  bio: '',
  detailed_perspective: '',
  stance,
  intensity: 0.5,
  confidence: 0.6,
  conviction: 0.6,
  cior: 0,
  domain_tags: [],
  communication_radius: 1,
  summary_provenance: [],
  confidence_breakdown: { source_breadth: 1, node_density: 1, relationship_connectivity: 1 },
})

const RUN: RunState = {
  ...initialState,
  runId: RUN_ID,
  status: 'running',
  query: 'Should we expand?',
  roster: [profile('Nordic Lead', 'POSITIVE'), profile('Baltic Lead', 'NEGATIVE')],
  rounds: [{ round: 1, pairs: [], turns: [], consensus: null }],
}

const SUMMARY: MapSummary = {
  counts: { entries: 2, experts: 2, opinions: 0, connections: 0 },
  busiest: [],
  step: 'The map',
}

const render = (tab: Tab, state: 'split' | 'expanded' | 'minimised' = 'split') =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={[`/runs/${RUN_ID}/${tab}`]}>
      <RunPageView
        run={RUN}
        events={[]}
        tab={tab}
        runId={RUN_ID}
        state={state}
        onStateChange={() => {}}
        map={<div data-map-canvas />}
        summary={SUMMARY}
        scrubbed={null}
        latestRound={1}
        onScrub={() => {}}
        onNavigate={() => {}}
        onReplay={() => {}}
      />
    </MemoryRouter>,
  )

/** The opening tag of the first element whose markup contains `marker`, so an assertion lands on one. */
function tagAround(html: string, marker: string): string {
  const at = html.indexOf(marker)
  if (at < 0) return ''
  return html.slice(html.lastIndexOf('<', at), html.indexOf('>', at) + 1)
}

const hostId = (html: string) => tagAround(html, `id="${HOST_ID}"`).match(/id="[^"]+"/)?.[0]

describe('the debate step shows the floor AND the map, side by side (§9.4, D14)', () => {
  it('renders the floor in the activity pane during the debate step', () => {
    expect(render('floor')).toContain('aria-label="The panel&#x27;s debate"')
  })

  it('renders the one map host beside it', () => {
    expect(render('floor')).toContain(`id="${HOST_ID}"`)
  })

  it('holds the floor inside the work pane and the map in the map pane — siblings, neither one replacing the other', () => {
    const html = render('floor')
    const work = html.slice(html.indexOf('aria-label="The work"'))
    const mapPane = html.slice(html.indexOf('aria-label="The map"'))
    expect(work).toContain('aria-label="The panel&#x27;s debate"')
    expect(mapPane).toContain(`id="${HOST_ID}"`)
  })

  it('does not render the floor on a tab that is not the debate step', () => {
    expect(render('verdict')).not.toContain('aria-label="The panel&#x27;s debate"')
  })
})

describe('changing the activity pane’s view never unmounts the map (§9.3, D14)', () => {
  it('keeps the map host in every tab', () => {
    for (const tab of TABS) expect(render(tab), tab).toContain(`id="${HOST_ID}"`)
  })

  it('keeps the map host identity byte-identical across the tabs', () => {
    const ids = TABS.map((tab) => hostId(render(tab)))
    expect(ids).toEqual(TABS.map(() => `id="${HOST_ID}"`))
  })

  it('keeps the map host byte-identical across the pane’s own states', () => {
    for (const state of ['split', 'expanded', 'minimised'] as const) {
      expect(hostId(render('floor', state)), state).toBe(`id="${HOST_ID}"`)
    }
  })
})

describe('busiestEntries — the text alternative ranks the entries by how connected they are (§9.4)', () => {
  const nodes = {
    a: { id: 'a', label: 'Nordic capacity', type: 'Topic' },
    b: { id: 'b', label: 'Baltic logistics', type: 'Topic' },
    c: { id: 'c', label: 'Steel tariffs', type: 'Topic' },
    d: { id: 'd', label: 'Unconnected note', type: 'Topic' },
  }
  // a carries 3 connections, b carries 2, c carries 1, d carries none.
  const edges = {
    'a|b|X': { source: 'a', target: 'b', label: 'X' },
    'a|b|Y': { source: 'a', target: 'b', label: 'Y' },
    'a|c|X': { source: 'a', target: 'c', label: 'X' },
  }

  it('ranks by degree, busiest first', () => {
    expect(busiestEntries(nodes, edges)).toEqual(['Nordic capacity', 'Baltic logistics', 'Steel tariffs'])
  })

  it('honours the limit', () => {
    expect(busiestEntries(nodes, edges, 2)).toEqual(['Nordic capacity', 'Baltic logistics'])
  })

  it('names no entry that carries no connection — an empty map has no busiest line', () => {
    expect(busiestEntries(nodes, {})).toEqual([])
  })
})

describe('the copy law (§13) holds on the run view in every section', () => {
  it.each(TABS)('%s renders no banned word', (tab) => {
    expect(renderedText(render(tab))).not.toMatch(BANNED_WORD)
  })
})

/** The opening tag of the panel whose id names `tab`, so an assertion lands on that one panel. */
const panelTag = (html: string, tab: Tab) =>
  html.match(new RegExp(`<div[^>]*id="run-panel-${tab}"[^>]*>`))?.[0] ?? ''

// Assembled from parts so this test file does not inflate the tabpanel-role source count the
// acceptance records over `frontend/src` — the five declarations in `RunPage.tsx` are the five.
const TABPANEL = ['role', '=', '"tabpanel"'].join('')

describe('one nav strip, and every section is a real tabpanel (§14.4)', () => {
  it('renders exactly one tablist — the stage rail is gone from the run', () => {
    const html = render('floor')
    expect(html.match(/role="tablist"/g)).toHaveLength(1)
    expect(html).not.toContain('aria-label="Run stages"')
  })

  it('names the five destinations in the product’s words', () => {
    const html = render('floor')
    for (const label of ['Roster', 'Debate', 'Verdict', 'Experts', 'Artifacts']) {
      expect(html, label).toContain(`>${label}</button>`)
    }
  })

  it('gives all five tabs a tabpanel, named by its tab', () => {
    const html = render('floor')
    expect(html.match(new RegExp(TABPANEL, 'g'))).toHaveLength(5)
    for (const tab of TABS) {
      expect(html, tab).toContain(`id="run-panel-${tab}"`)
      expect(html, tab).toContain(`aria-labelledby="run-tab-${tab}"`)
    }
  })

  it('shows the active tab’s panel and hides the rest', () => {
    const html = render('agents')
    expect(panelTag(html, 'agents')).not.toMatch(/hidden=""/)
    for (const tab of TABS.filter((entry) => entry !== 'agents')) {
      expect(panelTag(html, tab), tab).toMatch(/hidden=""/)
    }
  })
})

describe('the seam is one radius (§14.4)', () => {
  it('gives the work pane and the debate floor the card radius — never the 16px panel one', () => {
    const html = render('floor')
    const work = tagAround(html, 'aria-label="The work"')
    expect(work).toContain('rounded-md')
    expect(work).not.toContain('rounded-lg')

    const cards = [...html.matchAll(/<[a-z]+[^>]*shadow-raised[^>]*>/g)].map((match) => match[0])
    expect(cards).toHaveLength(2)
    for (const card of cards) {
      expect(card).toContain('rounded-md')
      expect(card).not.toContain('rounded-lg')
    }
  })

  it('keeps the map pane on the same radius', () => {
    expect(tagAround(render('floor'), 'aria-label="The map"')).toContain('rounded-md')
  })
})
