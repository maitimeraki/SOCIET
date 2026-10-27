/* eslint-disable react-refresh/only-export-components -- this module deliberately exports its pure helpers (the step resolver, the exported pure view) so the no-DOM suite can drive each step without a renderer. */
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import StageRail from '../components/common/StageRail'
import { useDraftStore } from '../wizard/draftStore'
import IngestPage from './IngestPage'
import GraphPage from './GraphPage'
import SocietyPage from './SocietyPage'
import { STEP_LABELS, STEPS, stepFromParam } from './workspaceSteps'
import type { WorkspaceStep } from './workspaceSteps'

// Re-exported so existing imports (`./NewRunWorkspace`) keep working after the move.
export { stepFromParam }
export type { WorkspaceStep }

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
  /** True when the current step has failed — its rail stage carries the danger marker, not a pulse. */
  failed?: boolean
}

/**
 * The pure view — the step is a prop, so the no-DOM suite renders each step to static markup
 * (Rulings F17/F23). The map and the pane geometry belong to `WorkspaceShell`; the page renders only
 * its step content.
 */
export function NewRunWorkspaceView({ step, failed = false }: NewRunWorkspaceViewProps) {
  return <StepWork step={step} failed={failed} />
}

const EXPIRED_NOTE = "Your session's documents expired — add them again."

/**
 * §9 The new-decision host. It owns the step (from `?step=`, F22) and reports a step failure to the
 * rail; the map host and the load/socket lifetime live in `WorkspaceShell`.
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

  return (
    <StepWork
      step={step}
      failed={step === 'graph' && failed}
      onFailureChange={setFailed}
    />
  )
}
