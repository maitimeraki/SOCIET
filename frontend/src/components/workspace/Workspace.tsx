import { useEffect, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import ActivityPane from './ActivityPane'
import GraphPane from './GraphPane'
import SplitDivider, { DEFAULT_RATIO, ratioFromKey } from './SplitDivider'
import { mirrorScroll, shouldMirror } from './syncScroll'
import { paneStateFrom, paneStorageKey, type PaneState } from './paneState'

export type { PaneState }

/** §2.4 The map's counts, by kind, as the text alternative reads them. Internal keys; the copy law
 *  governs the rendered labels, which `GraphPane` owns. */
export interface MapCounts {
  entries: number
  experts: number
  opinions: number
  connections: number
}

/** §9.4/§12 The accessible reading of the map: counts by kind, the busiest entries, the current step. */
export interface MapSummary {
  counts: MapCounts
  busiest: string[]
  step: string
}

export interface WorkspaceProps {
  /** The run or session id — the persistence key and the map host's id both hang off it. */
  mapId: string
  /** The map surface (`GraphCanvas`). Rendered once and kept mounted across every state. */
  map: ReactNode
  /** The work surface (the step's activity). */
  work: ReactNode
  summary: MapSummary
}

/**
 * §9 The stateful workspace. It owns nothing but the pane geometry, which it persists per run — the
 * layout itself lives in `WorkspaceView` so every state can be asserted from static markup (Ruling F17).
 */
export default function Workspace({ mapId, map, work, summary }: WorkspaceProps) {
  const [state, setState] = useState<PaneState>(() => {
    const stored = typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(paneStorageKey(mapId))
    const narrow = typeof matchMedia === 'function' && matchMedia('(max-width: 640px)').matches
    return paneStateFrom(stored, narrow)
  })
  const [ratio, setRatio] = useState(() =>
    ratioFromKey(typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(ratioStorageKey(mapId))),
  )

  useEffect(() => {
    if (typeof sessionStorage !== 'undefined') sessionStorage.setItem(paneStorageKey(mapId), state)
  }, [mapId, state])

  useEffect(() => {
    if (typeof sessionStorage !== 'undefined') sessionStorage.setItem(ratioStorageKey(mapId), String(ratio))
  }, [mapId, ratio])

  return (
    <WorkspaceView
      mapId={mapId}
      state={state}
      onStateChange={setState}
      map={map}
      work={work}
      summary={summary}
      ratio={ratio}
      onRatioChange={setRatio}
    />
  )
}

/** The split's share of the width, alongside the pane state under the same `chamber.workspace.*` key. */
const ratioStorageKey = (mapId: string) => `${paneStorageKey(mapId)}.ratio`

export interface WorkspaceViewProps extends WorkspaceProps {
  state: PaneState
  onStateChange: (next: PaneState) => void
  /** The map's share of the split, 0.3–0.7; it opens at 0.4 (§7.7). */
  ratio?: number
  onRatioChange?: (next: number) => void
}

/**
 * The pure view — pane state as a prop, so it renders to static markup without a DOM (Ruling F17).
 *
 * The two panes are siblings laid out by class, never conditionally rendered: the map host is a child
 * of `GraphPane` in every state, and the activity pane is hidden with `hidden` in expanded. That is the
 * construction under which "restore never re-fetches" and "focus stays on the toggle" hold — no state
 * change can unmount or remount either surface.
 */
export function WorkspaceView({
  mapId,
  state,
  onStateChange,
  map,
  work,
  summary,
  ratio = DEFAULT_RATIO,
  onRatioChange = () => {},
}: WorkspaceViewProps) {
  // Stacked below `lg` (flex column), the full-width three-column split from `lg` up (grid): the map
  // takes `--map-w`, the seam is one 1px track, the output takes the rest. In split the horizontal
  // gap is dropped from `lg` up, so the one rule is the whole seam (§10.3).
  const split = state === 'split'
  const outRef = useRef<HTMLDivElement | null>(null)
  const entriesRef = useRef<HTMLDivElement | null>(null)

  // §10.3 — the two sides scroll together, by proportion. Either side may lead; the caller assigns
  // only when the difference is more than a pixel, which is what stops the panes from chasing each
  // other round a loop. The map's scrolling half is its entries list, so the plot stays put.
  useEffect(() => {
    const out = outRef.current
    const entries = entriesRef.current
    if (!out || !entries) return
    const link = (from: HTMLDivElement, to: HTMLDivElement) => () => {
      const target = mirrorScroll(from, to)
      if (shouldMirror(to.scrollTop, target)) to.scrollTop = target
    }
    const outToEntries = link(out, entries)
    const entriesToOut = link(entries, out)
    out.addEventListener('scroll', outToEntries, { passive: true })
    entries.addEventListener('scroll', entriesToOut, { passive: true })
    return () => {
      out.removeEventListener('scroll', outToEntries)
      entries.removeEventListener('scroll', entriesToOut)
    }
  }, [])

  return (
    <div
      className={`flex min-h-0 flex-1 flex-col gap-4 ${
        split
          ? 'lg:grid lg:grid-cols-[var(--map-w,40%)_1px_minmax(0,1fr)] lg:grid-rows-[minmax(0,1fr)] lg:gap-x-0'
          : ''
      }`}
      style={split ? ({ '--map-w': `${ratio * 100}%` } as CSSProperties) : undefined}
    >
      {/* The work sits above the map whenever the panes stack (§9 responsive); only the wide split
          reorders it to the right. Each pane rides in its own order wrapper so the outer layout owns
          the order, not the panes. */}
      <div ref={outRef} className={split ? 'order-1 min-h-0 overflow-auto lg:order-3' : 'order-1'}>
        <ActivityPane hidden={state === 'expanded'}>{work}</ActivityPane>
      </div>
      {split && <SplitDivider ratio={ratio} onChange={onRatioChange} />}
      <div className={split ? 'order-2 min-h-0 overflow-auto lg:order-1' : 'order-2'}>
        <GraphPane
          mapId={mapId}
          state={state}
          onStateChange={onStateChange}
          summary={summary}
          entriesRef={entriesRef}
        >
          {map}
        </GraphPane>
      </div>
    </div>
  )
}
