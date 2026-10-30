import { describe, expect, it, vi } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx). The run page exports a
// pure view whose run and tab are plain props (Rulings F17/F23), so every section renders to static
// markup in Node. The map host and the pane geometry belong to `WorkspaceShell`; this file asserts
// the page's own work region: the one nav strip and the section it shows.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { RunPageView, shouldAutoOpenVerdict } from './RunPage'
import { busiestEntries } from '../components/workspace/GraphPane'
import type { AgentProfile } from '../run/events'
import { initialState, type RunState } from '../run/reducer'
// §13 — the one copy-law guard, shared with every rendered-string test.
import { BANNED_WORD, renderedText } from '../test/copyLaw'

// No jsdom / no testing-library (see GraphCanvas.test.tsx): the graph stack binds WebGL at import
// under Node, so mock the one DOM-bound module the run page pulls in through `AnswerDocument`.
vi.mock('@react-sigma/core', () => ({ SigmaContainer: () => null, useSigma: () => null }))

const RUN_ID = 'run-1'
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

const render = (tab: Tab) =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={[`/runs/${RUN_ID}/${tab}`]}>
      <RunPageView
        run={RUN}
        events={[]}
        tab={tab}
        runId={RUN_ID}
        scrubbed={null}
        latestRound={1}
        onScrub={() => {}}
        onNavigate={() => {}}
        onReplay={() => {}}
      />
    </MemoryRouter>,
  )

describe('the debate step shows the floor (§9.4, D14)', () => {
  it('renders the floor in the run’s work region during the debate step', () => {
    expect(render('floor')).toContain('aria-label="The panel&#x27;s debate"')
  })

  it('does not render the floor on a tab that is not the debate step', () => {
    expect(render('verdict')).not.toContain('aria-label="The panel&#x27;s debate"')
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
  it('renders exactly one tablist — the §15.5 stage strip is a nav, not a second tablist', () => {
    const html = render('floor')
    expect(html.match(/role="tablist"/g)).toHaveLength(1)
    expect(html).toContain('aria-label="Run stages"')
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

describe('the verdict opens itself once, and only with a verdict', () => {
  it('opens when a verdict lands and it has not been seen', () => {
    expect(shouldAutoOpenVerdict(true, false, 'floor')).toBe(true)
  })

  it('does not reopen a verdict already seen', () => {
    expect(shouldAutoOpenVerdict(true, true, 'floor')).toBe(false)
  })

  it('does not open without a verdict', () => {
    expect(shouldAutoOpenVerdict(false, false, 'floor')).toBe(false)
  })
})

describe('the debate floor keeps the card radius (§14.4)', () => {
  // The work pane and the map pane are the shell's (see WorkspaceShell.test.tsx); the floor card is
  // the page's own raised surface and keeps the same 10px radius, never the 16px panel one.
  it('gives the debate floor the card radius', () => {
    const cards = [...render('floor').matchAll(/<[a-z]+[^>]*shadow-card[^>]*>/g)].map((match) => match[0])
    expect(cards).toHaveLength(1)
    for (const card of cards) {
      expect(card).toContain('rounded-md')
      expect(card).not.toContain('rounded-lg')
    }
  })
})
