import type { RunState } from '../../run/reducer'
import { verdictView } from '../../run/selectors'
import type { ReportModel } from './exportReport'

/**
 * §12.8 / R57 — the one derivation of the filed report from folded run state. The report tab renders
 * this model and every export serializes it, so there is no second writer to drift.
 *
 * Null before a verdict is filed: the tab says the report is not there yet rather than inventing one.
 */
export function reportFromState(state: RunState): ReportModel | null {
  const view = verdictView(state)
  if (!view) return null
  return {
    title: view.title,
    reportStatus: view.reportStatus,
    markdown: view.markdown,
    sources: view.sources,
    warnings: view.warnings,
  }
}
