/* eslint-disable react-refresh/only-export-components -- this module deliberately exports its pure helpers (the step resolver, the exported pure view) so the no-DOM suite can drive each step without a renderer. */
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import GraphCanvas from '../components/graph/GraphCanvas'
import NodeDetailsDrawer from '../components/run/NodeDetailsDrawer'
import StageRail from '../components/common/StageRail'
import Workspace, { WorkspaceView } from '../components/workspace/Workspace'
import { mapCounts } from '../components/workspace/GraphPane'
import type { MapSummary, PaneState } from '../components/workspace/Workspace'
import { useDraftStore } from '../wizard/draftStore'
import { useGraphStore } from '../graph/graphStore'
import IngestPage from './IngestPage'
import GraphPage from './GraphPage'
import SocietyPage from './SocietyPage'

/**
 * §9 The three lifecycle steps, in one workspace. The step is an internal identifier — its query
 * values (`ingest`/`graph`/`society`) are the ones the old step paths used and are exempt from §13;
 * only `STEP_LABELS` ever renders.
 */
export type WorkspaceStep = 'ingest' | 'graph' | 'society'

const STEPS: WorkspaceStep[] = ['ingest', 'graph', 'society']

const STEP_LABELS: Record<WorkspaceStep, string> = {
  ingest: 'Your material',
  graph: 'The map',
  society: 'Your question',
}

/** The step a `?step=` value names; anything else (absent, unknown) is the first step. */
export function stepFromParam(value: string | null): WorkspaceStep {
  return value === 'graph' || value === 'society' ? value : 'ingest'
}

/** The rail the current step drives (§9.4): earlier steps settle, the current runs, later wait — and
 *  a failed current step carries the danger marker, not a pulse that would contradict the body. */
function stepStages(current: WorkspaceStep, failed: boolean) {
  const at = STEPS.indexOf(current)
  return STEPS.map((key, index) => ({
    key,
    label: STEP_LABELS[key],
    state:
      index < at
        ? ('done' as const)
        : index === at
          ? failed
            ? ('failed' as const)
            : ('running' as const)
          : ('pending' as const),
  }))
}

function StepSurface({
  step,
  onFailureChange,
}: {
  step: WorkspaceStep
  onFailureChange?: (failed: boolean) => void
}) {
  if (step === 'graph') return <GraphPage onFailureChange={onFailureChange} />
  if (step === 'society') return <SocietyPage />
  return <IngestPage />
}

/** The step's surface under the step indicator — the activity pane's whole content (§9.4). */
function StepWork({
  step,
  failed,
  onFailureChange,
}: {
  step: WorkspaceStep
  failed: boolean
  onFailureChange?: (failed: boolean) => void
}) {
  return (
    <div className="space-y-6">
      <StageRail stages={stepStages(step, failed)} activeKey={step} />
      <StepSurface step={step} onFailureChange={onFailureChange} />
    </div>
  )
}

export interface NewRunWorkspaceViewProps {
  step: WorkspaceStep
  mapId: string
  state: PaneState
  onStateChange: (next: PaneState) => void
  map: ReactNode
  summary: MapSummary
  /** True when the current step has failed — its rail stage carries the danger marker, not a pulse. */
  failed?: boolean
}

/**
 * The pure view — the step AND the pane state are props, so the no-DOM suite renders each step to
 * static markup (Rulings F17/F23). The `map` node is handed to the pane's always-rendered host and
 * is never conditionally rendered, so no step change can unmount or remount it (Ruling F22).
 */
export function NewRunWorkspaceView({
  step,
  mapId,
  state,
  onStateChange,
  map,
  summary,
  failed = false,
}: NewRunWorkspaceViewProps) {
  return (
    <WorkspaceView
      mapId={mapId}
      state={state}
      onStateChange={onStateChange}
      map={map}
      summary={{ ...summary, step: STEP_LABELS[step] }}
      work={<StepWork step={step} failed={failed} />}
    />
  )
}

/** The workspace's map id for a new decision — stable across every step, so the map host never
 *  changes identity as the lifecycle advances. */
const SESSION_MAP_ID = 'new'
const EXPIRED_NOTE = "Your session's documents expired — add them again."

/**
 * §9 The new-decision host. It owns nothing but the step (from `?step=`, F22), the map node and the
 * map's text alternative — the pane geometry lives in `Workspace`. One route element renders every
 * step, so React reconciles the same component type at the same position: the map never remounts on
 * a step change, and the graph store is rendered across the whole lifecycle rather than surviving
 * navigation unshown.
 */
export default function NewRunWorkspace() {
  const [params] = useSearchParams()
  const step = stepFromParam(params.get('step'))
  const navigate = useNavigate()
  // The build step reports its own failure up (it owns the phase machine); the rail reads it so the
  // indicator never says "running" beside the body's error. Gated to the graph step so a later step
  // cannot inherit a stale marker.
  const [failed, setFailed] = useState(false)

  const datasetId = useDraftStore((s) => s.datasetId)
  const graphJobId = useDraftStore((s) => s.graphJobId)
  const docs = useDraftStore((s) => s.docs)
  const readyCount = docs.filter((doc) => doc.status === 'ready').length

  // The no-documents guard, moved off the two step pages (they are no longer hosts, so their own
  // redirect would drop the note through `<Navigate>`): landing past the first step without a
  // corpus returns to it with the note IngestPage renders. The map step also needs one readable
  // document to build from.
  useEffect(() => {
    if (step === 'ingest') return
    const stale = !datasetId || (step === 'graph' && readyCount === 0)
    if (stale) navigate('/new?step=ingest', { replace: true, state: { note: EXPIRED_NOTE } })
  }, [step, datasetId, readyCount, navigate])

  const nodes = useGraphStore((s) => s.nodes)
  const edges = useGraphStore((s) => s.edges)
  // The text alternative reads the one store by kind, so all three layers count as they grow (§9.4).
  const summary: MapSummary = { counts: mapCounts(nodes, edges), busiest: [], step: STEP_LABELS[step] }

  const map = datasetId && graphJobId ? <GraphCanvas datasetId={datasetId} jobId={graphJobId} /> : null

  return (
    <>
      <Workspace
        mapId={SESSION_MAP_ID}
        map={map}
        work={<StepWork step={step} failed={step === 'graph' && failed} onFailureChange={setFailed} />}
        summary={summary}
      />
      {/* §9.5 The open entry's details. A sibling of the panes, never a child of the map host: the
          host is hidden when the map is minimised, and a dialog inside a hidden, aria-hidden subtree
          is not reachable. It draws nothing until an entry is opened. */}
      <NodeDetailsDrawer />
    </>
  )
}
