/**
 * §9 The three lifecycle steps, in one workspace. The step is an internal identifier — its query
 * values (`ingest`/`graph`/`society`) are the ones the old step paths used and are exempt from §13;
 * only `STEP_LABELS` ever renders.
 */
export type WorkspaceStep = 'ingest' | 'graph' | 'society'

export const STEPS: WorkspaceStep[] = ['ingest', 'graph', 'society']

export const STEP_LABELS: Record<WorkspaceStep, string> = {
  ingest: 'Your material',
  graph: 'The map',
  society: 'Your question',
}

/** The step a `?step=` value names; anything else (absent, unknown) is the first step. */
export function stepFromParam(value: string | null): WorkspaceStep {
  return value === 'graph' || value === 'society' ? value : 'ingest'
}
