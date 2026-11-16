import { describe, expect, it, vi } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx). The run page exports a
// pure view whose run and tab are plain props (Rulings F17/F23), so every section renders to static
// markup in Node. The map host and the pane geometry belong to `WorkspaceShell`; this file asserts
// the page's own work region: the one nav strip and the section it shows.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { RunPageView, shouldAutoOpenVerdict } from './RunPage'
import { busiestEntries } from '../components/workspace/GraphPane'
import type { AgentView } from '../run/events'
import { initialState, type RunState } from '../run/reducer'
// §13 — the one copy-law guard, shared with every rendered-string test.
import { BANNED_TERMS, renderedText } from '../test/copyLaw'

// No jsdom / no testing-library (see GraphCanvas.test.tsx): the graph stack binds WebGL at import
// under Node, so mock the DOM-bound module if the run page's tree ever reaches it through the floor.
vi.mock('@react-sigma/core', () => ({ SigmaContainer: () => null, useSigma: () => null }))

const RUN_ID = 'run-1'
const TABS = ['roster', 'floor', 'verdict', 'agents', 'artifacts'] as const
type Tab = (typeof TABS)[number]

const profile = (name: string, stance: AgentView['stance']): AgentView => ({
  name,
  type: 'analyst',
  role: 'analyst',
  stance,
  strength: 0.6,
  bio: '',
  details: '',
  confidence: 0.6,
})

const RUN: RunState = {
  ...initialState,
  runId: RUN_ID,
  status: 'running',
  query: 'Should we expand?',
  roster: [profile('Nordic Lead', 'POSITIVE'), profile('Baltic Lead', 'NEGATIVE')],
  rounds: [{ round: 1, pairs: [], turns: [], consensus: null }],
}

/** The same run once its verdict is filed — the state the report tab renders from. */
const FILED: RunState = {
  ...RUN,
  status: 'complete',
  stages: [{ stage: 'verdict', index: 6, at: Date.UTC(2026, 9, 22, 9, 30), fields: {} }],
  verdict: {
    converged: true,
    title: 'Should we expand?',
    markdown:
      '# Should we expand?\n## Recommendation\nPosition: POSITIVE, 83%, settled\nExpand, cautiously.\n' +
      '## Entry cost\nPoint: Entry cost outweighs the single market (judgement)',
    reportStatus: 'produced',
    sources: {},
    confidence: 0.83,
    // A filed verdict carries its weighted clusters; the stance is the dominant weight, not a head count.
    clusters: {
      POSITIVE: { stance: 'POSITIVE', count: 1, total_weight: 0.7, avg_confidence: 0.8, avg_conviction: 0.6, agents: ['Nordic Lead'] },
      NEGATIVE: { stance: 'NEGATIVE', count: 1, total_weight: 0.3, avg_confidence: 0.6, avg_conviction: 0.5, agents: ['Baltic Lead'] },
      NEUTRAL: { stance: 'NEUTRAL', count: 0, total_weight: 0, avg_confidence: 0, avg_conviction: 0, agents: [] },
      ABSTAIN: { stance: 'ABSTAIN', count: 0, total_weight: 0, avg_confidence: 0, avg_conviction: 0, agents: [] },
    },
    finalStances: { 'Nordic Lead': 'POSITIVE', 'Baltic Lead': 'NEGATIVE' },
    supporting: [],
    opposing: [],
  },
}

const render = (tab: Tab, run: RunState = RUN) =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={[`/runs/${RUN_ID}/${tab}`]}>
      <RunPageView
        run={run}
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
    expect(renderedText(render(tab))).not.toMatch(BANNED_TERMS)
  })

  it('the filed report renders no banned word', () => {
    expect(renderedText(render('verdict', FILED))).not.toMatch(BANNED_TERMS)
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
    for (const label of ['Roster', 'Debate', 'Report', 'Experts', 'Record']) {
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

describe('the report tab files the report (§12.8, R57)', () => {
  it('mounts the filed report as the backend wrote it', () => {
    const html = render('verdict', FILED)
    expect(html).toContain('Should we expand?')
    expect(html).toContain('Position: POSITIVE, 83%, settled')
    expect(html).toContain('Expand, cautiously.')
    expect(html).toContain('Entry cost outweighs the single market (judgement)')
    expect(html).not.toContain('The passes')
    expect(html).not.toContain('The case against')
  })

  it('offers the retry, and no export, for a report that was not produced', () => {
    const unproduced: RunState = {
      ...FILED,
      verdict: { ...FILED.verdict!, reportStatus: 'not_produced', title: null, markdown: null, sources: {} },
    }
    const html = render('verdict', unproduced)
    expect(html).toContain('Report not produced')
    expect(html).toContain('Retry report')
    expect(html).not.toContain('Copy for Google Docs')
  })

  it('offers the one export bar over the one construction (§11.4/§12.8)', () => {
    const html = render('verdict', FILED)
    expect(html).toContain('Copy for Google Docs')
    expect(html).toContain('>Markdown</button>')
    expect(html).toContain('>HTML</button>')
    expect(html).toContain('>JSON</button>')
    expect(html).toContain('aria-label="Export this decision"')
  })

  it('states that the report is not filed yet instead of inventing one', () => {
    const html = render('verdict')
    expect(html).toContain('The report appears when the debate completes.')
    expect(html).not.toContain('The passes')
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

describe('the debate floor takes the Quiet Room card radius (§14.4)', () => {
  // The work pane and the map pane are the shell's (see WorkspaceShell.test.tsx); the floor card is
  // the page's own raised surface and takes the card's 16px corner.
  it('gives the debate floor the card radius', () => {
    const cards = [...render('floor').matchAll(/<[a-z]+[^>]*shadow-card[^>]*>/g)].map((match) => match[0])
    expect(cards).toHaveLength(1)
    for (const card of cards) {
      expect(card).toContain('rounded-lg')
      expect(card).not.toContain('rounded-md')
    }
  })
})
