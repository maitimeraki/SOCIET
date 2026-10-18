/* eslint-disable react-refresh/only-export-components -- this module deliberately exports its pure helpers (the step resolver, the exported pure view) so the no-DOM suite can drive each step without a renderer. */
import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import GraphCanvas from '../components/graph/GraphCanvas'
import StageRail from '../components/common/StageRail'
import Workspace, { WorkspaceView } from '../components/workspace/Workspace'
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

/** The rail the current step drives (§9.4): earlier steps settle, the current runs, later wait. */
function stepStages(current: WorkspaceStep) {
  const at = STEPS.indexOf(current)
  return STEPS.map((key, index) => ({
    key,
    label: STEP_LABELS[key],
    state: index < at ? ('done' as const) : index === at ? ('running' as const) : ('pending' as const),
  }))
}

function StepSurface({ step }: { step: WorkspaceStep }) {
  if (step === 'graph') return <GraphPage />
  if (step === 'society') return <SocietyPage />
  return <IngestPage />
}

/** The step's surface under the step indicator — the activity pane's whole content (§9.4). */
function StepWork({ step }: { step: WorkspaceStep }) {
  return (
    <div className="space-y-6">
      <StageRail stages={stepStages(step)} activeKey={step} />
      <StepSurface step={step} />
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
}

/**
 * The pure view — the step AND the pane state are props, so the no-DOM suite renders each step to
 * static markup (Rulings F17/F23). The `map` node is handed to the pane's always-rendered host and
 * is never conditionally rendered, so no step change can unmount or remount it (Ruling F22).
 */
export function NewRunWorkspaceView({ step, mapId, state, onStateChange, map, summary }: NewRunWorkspaceViewProps) {
  return (
    <WorkspaceView
      mapId={mapId}
      state={state}
      onStateChange={onStateChange}
      map={map}
      summary={{ ...summary, step: STEP_LABELS[step] }}
      work={<StepWork step={step} />}
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
  const summary: MapSummary = {
    // The corpus layer is the map today; the expert and opinion layers arrive in Phase 4 (Task 4.0).
    counts: { entries: Object.keys(nodes).length, experts: 0, opinions: 0, connections: Object.keys(edges).length },
    busiest: [],
    step: STEP_LABELS[step],
  }

  const map = datasetId && graphJobId ? <GraphCanvas datasetId={datasetId} jobId={graphJobId} /> : null

  return <Workspace mapId={SESSION_MAP_ID} map={map} work={<StepWork step={step} />} summary={summary} />
}
