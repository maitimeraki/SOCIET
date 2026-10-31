/**
 * §9 The three lifecycle steps, in one workspace. The step is an internal identifier — its query
 * values (`ingest`/`graph`/`society`) are the ones the old step paths used and are exempt from §13;
 * only `STEP_LABELS` ever renders.
 */
export type WorkspaceStep = 'ingest' | 'graph' | 'society'

/**
 * §7.7 The workspace's one label map: the lifecycle steps the in-flow rail names, and the top bar's
 * three words (`material`/`question`/`panel`). The top bar's keys are words, not query values — the
 * route still speaks `WorkspaceStep` (R13).
 */
export type WorkspaceStage = WorkspaceStep | 'material' | 'question' | 'panel'

export const STEPS: WorkspaceStep[] = ['ingest', 'graph', 'society']

export const STEP_LABELS: Record<WorkspaceStage, string> = {
  ingest: 'Your material',
  graph: 'The map',
  society: 'Your question',
  // The top bar's indicator is three capitalised dots (R58); the rail keeps the longer sentence labels.
  material: 'Material',
  question: 'Question',
  panel: 'Panel',
}

/** The step a `?step=` value names; anything else (absent, unknown) is the first step. */
export function stepFromParam(value: string | null): WorkspaceStep {
  return value === 'graph' || value === 'society' ? value : 'ingest'
}
