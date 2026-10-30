import { useEffect, useRef, Suspense } from 'react'
import { Outlet, useLocation, useMatch, useSearchParams } from 'react-router-dom'
import AppErrorBoundary from '../AppErrorBoundary'
import GraphCanvas from '../graph/GraphCanvas'
import NodeDetailsDrawer from '../run/NodeDetailsDrawer'
import Workspace from '../workspace/Workspace'
import { busiestEntries, mapCounts } from '../workspace/GraphPane'
import { useDraftStore } from '../../wizard/draftStore'
import { useGraphStore } from '../../graph/graphStore'
import { useRunStore } from '../../run/runStore'
import { STEP_LABELS, stepFromParam } from '../../pages/workspaceSteps'
import { RouteFallback } from './AppShell'
import WorkspaceTopBar from './WorkspaceTopBar'

/**
 * §9 The full-screen workspace shell. One layout route for the new-decision lifecycle AND every run,
 * so the one map host is mounted above the pages: switching step, tab or run reconciles the same
 * pane geometry, and the canvas is never unmounted by a page change (Ruling F22, D14).
 *
 * The shell owns what the pages used to duplicate — the map surface, its text alternative, the load
 * and socket lifetime, and the details drawer. Pages render only their activity content.
 *
 * The layout route is pathless, so `useParams` cannot see the child's `:runId`; the run id is read
 * off the matched path instead.
 */
export default function WorkspaceShell() {
  const runMatch = useMatch('/runs/:runId/*')
  const runId = runMatch?.params.runId
  const location = useLocation()
  const [params] = useSearchParams()
  const step = stepFromParam(params.get('step'))
  const datasetId = useDraftStore((state) => state.datasetId)
  const graphJobId = useDraftStore((state) => state.graphJobId)
  const run = useRunStore((state) => state.run)
  const loadAndConnect = useRunStore((state) => state.loadAndConnect)
  const corpusMissing = useRunStore((state) => state.corpusMissing)
  const nodes = useGraphStore((state) => state.nodes)
  const edges = useGraphStore((state) => state.edges)

  // The handoff is consumed ONCE per run, at the moment the run id changes. It must not re-run when a
  // later navigation drops `location.state` (every tab click, the roster→floor replace): that would
  // reload the run and `seedMap()` over the extraction map the handoff exists to preserve.
  const handoffForRun = useRef<{ runId: string; keepMap: boolean } | null>(null)

  useEffect(() => {
    if (!runId) {
      // Left the run for the new-decision workspace — the old `RunPage` unmount lifetime, restored.
      useRunStore.getState().disconnect()
      handoffForRun.current = null
      return
    }
    if (handoffForRun.current?.runId !== runId) {
      handoffForRun.current = {
        runId,
        keepMap: Boolean((location.state as { handoff?: boolean } | null)?.handoff),
      }
    }
    void loadAndConnect(runId, { keepMap: handoffForRun.current.keepMap })
    // `location` is read only when the run changes; depending on it would re-run on every navigation
    // and defeat the once-per-run handoff.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, loadAndConnect])

  useEffect(() => () => useRunStore.getState().disconnect(), [])

  const mapId = runId ?? 'new'
  const map = runId ? (
    // The wrapper is a growing flex child of the map host, not a plain block: `GraphCanvas`'s
    // `flex-1` needs the wrapper to have a definite height, or the plot collapses to 1px.
    <div className="relative flex min-h-0 flex-1 flex-col">
      <GraphCanvas datasetId={run.datasetId ?? ''} />
      {/* The material read found nothing — said in words IN the map's own region, over a map that
          is not blank (the run's experts and opinions still stand), never a silent empty map. */}
      {corpusMissing && (
        <div className="absolute inset-0 flex items-center justify-center bg-map-ground/90 p-6">
          <p role="status" className="max-w-sm text-center text-body text-ink-2">
            The material behind this decision is no longer available.
          </p>
        </div>
      )}
    </div>
  ) : datasetId && graphJobId ? (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <GraphCanvas datasetId={datasetId} jobId={graphJobId} />
    </div>
  ) : null
  const summary = {
    counts: mapCounts(nodes, edges),
    busiest: busiestEntries(nodes, edges),
    step: runId ? STEP_LABELS.graph : STEP_LABELS[step],
  }
  const title = runId ? run.query || 'This decision' : STEP_LABELS[step]

  return (
    <div className="flex min-h-screen flex-col bg-bone">
      <a href="#content" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[70] focus:inline-flex focus:min-h-11 focus:items-center focus:rounded-sm focus:bg-paper focus:px-3 focus:py-2 focus:text-body focus:text-ink">
        Skip to content
      </a>
      <WorkspaceTopBar title={title} />
      <main id="content" className="min-w-0 flex-1 px-4 pb-8 pt-4">
        <AppErrorBoundary key={runId ?? 'new'}>
          <Workspace
            mapId={mapId}
            map={map}
            summary={summary}
            work={
              <Suspense fallback={<RouteFallback />}>
                <Outlet />
              </Suspense>
            }
          />
        </AppErrorBoundary>
      </main>
      <NodeDetailsDrawer />
    </div>
  )
}
