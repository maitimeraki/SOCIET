import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): the workspace is split
// into a stateful wrapper and an exported pure VIEW whose pane state is a plain prop (Ruling F17), so
// each state renders to static markup in Node. Focus return and "no re-fetch on restore" are NOT
// assertable without a DOM — they are satisfied by construction (the map host is never conditionally
// rendered or remounted) and stated as such, never faked with a simulated click.
import { renderToStaticMarkup } from 'react-dom/server'
import { WorkspaceView, type MapSummary, type PaneState } from './Workspace'
import { paneStateFrom, paneStorageKey } from './paneState'
// §13 — the one copy-law guard, shared with every rendered-string test.
import { BANNED_WORD, renderedText } from '../../test/copyLaw'

const MAP_ID = 'run-1'
const HOST_ID = `workspace-map-${MAP_ID}`

const SUMMARY: MapSummary = {
  counts: { entries: 12, experts: 4, opinions: 7, connections: 9 },
  busiest: ['Nordic capacity', 'Baltic logistics'],
  step: 'Your question',
}

const render = (state: PaneState) =>
  renderToStaticMarkup(
    <WorkspaceView
      mapId={MAP_ID}
      state={state}
      onStateChange={() => {}}
      map={<div data-map-canvas />}
      work={<p>the work region</p>}
      summary={SUMMARY}
    />,
  )

/** The opening tag of the first element whose markup contains `marker`, so an assertion lands on one. */
function tagAround(html: string, marker: string): string {
  const at = html.indexOf(marker)
  if (at < 0) return ''
  return html.slice(html.lastIndexOf('<', at), html.indexOf('>', at) + 1)
}

const hostTag = (html: string) => tagAround(html, `id="${HOST_ID}"`)

describe('paneStateFrom — the default and the phone default', () => {
  it('split is the default with nothing stored', () => {
    expect(paneStateFrom(null)).toBe('split')
  })

  it('minimises by default on a narrow viewport', () => {
    expect(paneStateFrom(null, true)).toBe('minimised')
  })

  it('a stored state wins over the default', () => {
    expect(paneStateFrom('expanded')).toBe('expanded')
  })

  it('an unrecognised stored value falls back to split', () => {
    expect(paneStateFrom('sideways')).toBe('split')
  })

  it('the key follows the chamber.* convention, keyed by the run', () => {
    expect(paneStorageKey('run-1')).toBe('chamber.workspace.run-1')
  })
})

describe('the map pane is present in every state — it never unmounts (§9.3, Ruling F17)', () => {
  it('renders the map host in split', () => {
    expect(render('split')).toContain(`id="${HOST_ID}"`)
  })

  it('renders the map host in expanded', () => {
    expect(render('expanded')).toContain(`id="${HOST_ID}"`)
  })

  it('renders the map host in minimised — hidden, never unmounted', () => {
    expect(render('minimised')).toContain(`id="${HOST_ID}"`)
  })

  it('hides the map host with `hidden` in minimised rather than removing it', () => {
    expect(hostTag(render('minimised'))).toMatch(/ hidden=""/)
  })

  it('keeps the map host visible (no `hidden`) in split', () => {
    expect(hostTag(render('split'))).not.toMatch(/ hidden=""/)
  })

  it('keeps the map host visible (no `hidden`) in expanded', () => {
    expect(hostTag(render('expanded'))).not.toMatch(/ hidden=""/)
  })

  it('keeps the map host identity the same across all three states', () => {
    const ids = (['split', 'expanded', 'minimised'] as const).map((s) => hostTag(render(s)).match(/id="[^"]+"/)?.[0])
    expect(ids).toEqual([`id="${HOST_ID}"`, `id="${HOST_ID}"`, `id="${HOST_ID}"`])
  })
})

describe('the pane controls are real buttons wired to the map host (§12)', () => {
  it('offers a real minimise button with aria-expanded and aria-controls in split', () => {
    const tag = tagAround(render('split'), 'aria-label="Minimise the map"')
    expect(tag).toContain('<button')
    expect(tag).toContain('aria-expanded="true"')
    expect(tag).toContain(`aria-controls="${HOST_ID}"`)
  })

  it('offers a real expand button with aria-expanded and aria-controls in split', () => {
    const tag = tagAround(render('split'), 'aria-label="Expand the map"')
    expect(tag).toContain('<button')
    expect(tag).toContain('aria-expanded="false"')
    expect(tag).toContain(`aria-controls="${HOST_ID}"`)
  })

  it('replaces expand with restore-the-split once the map is expanded', () => {
    const tag = tagAround(render('expanded'), 'aria-label="Restore the split"')
    expect(tag).toContain('<button')
    expect(tag).toContain(`aria-controls="${HOST_ID}"`)
  })

  it('offers a real restore button — collapsed — in minimised', () => {
    const tag = tagAround(render('minimised'), 'aria-label="Restore the map"')
    expect(tag).toContain('<button')
    expect(tag).toContain('aria-expanded="false"')
    expect(tag).toContain(`aria-controls="${HOST_ID}"`)
  })

  it('points aria-controls at the element that actually carries the id', () => {
    const html = render('split')
    expect(tagAround(html, 'aria-label="Minimise the map"')).toContain(`aria-controls="${HOST_ID}"`)
    expect(html).toContain(`id="${HOST_ID}"`)
  })
})

describe('the map has a text alternative — the map’s equal, not a fallback (§12)', () => {
  it('reads out the counts by kind', () => {
    const html = render('split')
    expect(html).toContain('12 entries')
    expect(html).toContain('4 experts')
    expect(html).toContain('7 opinions')
    expect(html).toContain('9 connections')
  })

  it('reads out the busiest entries and the current step', () => {
    const html = render('split')
    expect(html).toContain('Nordic capacity')
    expect(html).toContain('Your question')
  })

  it('exposes the reading in every state, including minimised', () => {
    expect(render('minimised')).toContain('12 entries')
  })
})

describe('the activity pane is the work; the map fills the region when expanded', () => {
  it('renders the work in split and in minimised', () => {
    expect(render('split')).toContain('the work region')
    expect(render('minimised')).toContain('the work region')
  })

  it('hides the work (by `hidden`, not by unmounting) when the map is expanded', () => {
    const tag = tagAround(render('expanded'), 'aria-label="The work"')
    expect(tag).toMatch(/ hidden=""/)
  })
})

describe('the split is resizable — the divider lives only in split (§9)', () => {
  it('renders the splitter only in split', () => {
    expect(render('split')).toContain('role="separator"')
    expect(render('expanded')).not.toContain('role="separator"')
    expect(render('minimised')).not.toContain('role="separator"')
  })

  it('draws the divider from the view’s ratio', () => {
    const html = renderToStaticMarkup(
      <WorkspaceView
        mapId={MAP_ID}
        state="split"
        onStateChange={() => {}}
        map={<div data-map-canvas />}
        work={<p>the work region</p>}
        summary={SUMMARY}
        ratio={0.3}
      />,
    )
    expect(html).toContain('aria-valuenow="30"')
  })
})

describe('the copy law (§13) governs every rendered string', () => {
  it('renders no banned word in any of the three states', () => {
    for (const state of ['split', 'expanded', 'minimised'] as const) {
      expect(renderedText(render(state)), state).not.toMatch(BANNED_WORD)
    }
  })
})
