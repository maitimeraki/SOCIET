/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import DashboardView from './dashboardView'
import type { DashboardViewProps } from './dashboardView'
import { DASHBOARD_ANCHORS } from './dashboardAnchors'
// §13 — the one copy-law guard, shared with every rendered-string test.
import { BANNED_WORD, renderedText } from '../test/copyLaw'

const render = (props: Partial<DashboardViewProps> = {}) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <DashboardView
        accountEmpty={false}
        live={null}
        material={<p>material body</p>}
        decisions={<p>decisions body</p>}
        lastAnswer={<p>answer body</p>}
        panel={<p>panel body</p>}
        {...props}
      />
    </MemoryRouter>,
  )

/** Every anchor in the markup — the actionable controls the acceptance counts. */
const anchors = (html: string): number => html.match(/<a\b/g)?.length ?? 0

describe('the dashboard — one surface, four sections in the lifecycle order', () => {
  it('renders the page title once, at text-display', () => {
    const html = render()
    expect(html.match(/<h1\b/g)).toHaveLength(1)
    expect(html).toMatch(/<h1[^>]*class="[^"]*text-display/)
    expect(html).toContain('Your account')
  })

  it('renders the four fixed section headings, in order, each at text-title', () => {
    const html = render()
    const order = ['Your material', 'Your decisions', 'The last answer', 'Your panel'].map((title) =>
      html.indexOf(`>${title}</h2>`),
    )
    expect(order.every((index) => index >= 0)).toBe(true)
    expect([...order].sort((a, b) => a - b)).toEqual(order)
    expect(html.match(/<h2[^>]*class="text-title text-ink"/g)).toHaveLength(4)
    // No third level between the page title and the section headings.
    expect(html).not.toMatch(/<h2[^>]*text-heading/)
  })

  it('carries an anchor id for each section, and the redirects resolve to the same ids', () => {
    const html = render()
    expect(html).toContain(`id="${DASHBOARD_ANCHORS.material}"`)
    expect(html).toContain(`id="${DASHBOARD_ANCHORS.decisions}"`)
    expect(html).toContain(`id="${DASHBOARD_ANCHORS.lastAnswer}"`)
    expect(html).toContain(`id="${DASHBOARD_ANCHORS.panel}"`)
  })

  it('separates every section with a rule, never whitespace alone', () => {
    const html = render()
    // The page title's rule, then one rule at every section boundary, then the closing rule.
    expect(html.match(/class="rule-b[^"]*"/g)?.length).toBeGreaterThanOrEqual(1)
    expect(html.match(/rule-y/g)?.length).toBeGreaterThanOrEqual(2)
  })

  it('uses one band only — plum on The last answer — and no other band tone', () => {
    const html = render()
    expect(html.match(/band--plum/g)).toHaveLength(1)
    expect(html).not.toMatch(/band--(?:band|sky|warm|dark|page)\b/)
    // The plum band is The last answer's own section.
    expect(html).toMatch(/class="band band--plum[^"]*"[^>]*id="last-answer"/)
  })

  it('renders the live band as one line, never a second floor', () => {
    const html = render({ live: { runId: 'r1', question: 'Should we open on Mill Street?' } })
    expect(html.match(/data-capture="live"/g)).toHaveLength(1)
    expect(html).toContain('Deliberating')
    expect(html).toContain('href="/runs/r1"')
    expect(html).toContain('Should we open on Mill Street?')
    expect(html).not.toContain('<canvas')
  })

  it('does not import the debate floor into the page', () => {
    // The one-line live band replaced the second ChamberFloor (§14.3's LIVE row).
    const source = readFileSync('src/pages/DashboardPage.tsx', 'utf8')
    expect(source).not.toContain('ChamberFloor')
  })
})

describe('the empty account — one state, one action', () => {
  it('renders exactly one actionable control', () => {
    const html = render({ accountEmpty: true })
    expect(anchors(html)).toBe(1)
    expect(html).toContain('href="/new"')
    expect(html).toContain('Start free')
  })

  it('renders one empty block, not four empty sections', () => {
    const html = render({ accountEmpty: true })
    expect(html).not.toContain(`id="${DASHBOARD_ANCHORS.material}"`)
    expect(html).not.toContain(`id="${DASHBOARD_ANCHORS.decisions}"`)
    expect(html).not.toContain(`id="${DASHBOARD_ANCHORS.lastAnswer}"`)
    expect(html).not.toContain(`id="${DASHBOARD_ANCHORS.panel}"`)
    expect(html).not.toContain('material body')
    expect(html).toContain('border-dashed') // the one ruled empty block
  })
})

describe('the dashboard speaks the new world', () => {
  it('carries no retired-world word, in any file — a comment counts too', () => {
    const files = [
      'src/pages/DashboardPage.tsx',
      'src/pages/dashboardView.tsx',
      'src/pages/dashboardCopy.ts',
      'src/pages/dashboardSubject.ts',
      'src/pages/dashboardAnchors.ts',
      'src/sections/DocumentsSection.tsx',
      'src/sections/RunsSection.tsx',
      'src/sections/ResultsSection.tsx',
      'src/sections/PanelSection.tsx',
      'src/components/common/RunTable.tsx',
      'src/components/shell/Rail.tsx',
    ]
    const retired = /traverse|\boperate\b|recent decisions|all decisions|start a decision|debating now|open the run/i
    expect(files.filter((file) => retired.test(readFileSync(file, 'utf8')))).toEqual([])
  })
})

describe('the copy law (§13) holds on the dashboard in every state', () => {
  it('renders no banned word, loaded, live, empty account or bare page', () => {
    expect(renderedText(render())).not.toMatch(BANNED_WORD)
    expect(
      renderedText(render({ live: { runId: 'r1', question: 'Should we open on Mill Street?' } })),
    ).not.toMatch(BANNED_WORD)
    expect(renderedText(render({ accountEmpty: true }))).not.toMatch(BANNED_WORD)
  })
})
