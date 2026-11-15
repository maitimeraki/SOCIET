import type { RunState } from '../../run/reducer'
import { STANCE_ORDER, convergenceSeries, verdictView } from '../../run/selectors'
import type { VerdictView } from '../../run/selectors'
import { splitSections } from '../verdict/narrative'
import { fmtDay } from '../../utils/format'
import type { ReportModel } from './exportReport'

/**
 * §12.8 / R57 — the one derivation of the filed report from folded run state. The report tab renders
 * this model and every export serializes it, so there is no second writer to drift.
 *
 * `filedAt` is the stored run doc's `created_at`, threaded from the store (R59). The event buffer
 * carries no timestamp of its own, so when the store has none the day is stated as not recorded —
 * never a fold clock passed off as the filing day.
 *
 * Null before a verdict is filed: the tab states that the report is not there yet rather than
 * fabricating one.
 */
export function reportFromState(state: RunState, filedAt: string | null): ReportModel | null {
  const view = verdictView(state)
  if (!view) return null
  return {
    question: state.query || 'This decision',
    filed: filedAt ? fmtDay(filedAt) : '—',
    // No position carries weight: the report says ABSTAIN, the same state the server files.
    position: view.stance ?? 'ABSTAIN',
    share: view.confidence,
    caseAgainst: view.dissentingViews[0]?.view ?? 'No dissent was recorded.',
    reasoning: reasoningOf(view),
    whoHeldWhichView: heldViews(view),
    // A pass with no consensus has no shares to chart, so it is left out rather than charted as zero.
    passes: convergenceSeries(state).flatMap((tick) =>
      tick.weights
        ? [{ pass: `P${tick.round}`, negative: tick.weights.NEGATIVE, positive: tick.weights.POSITIVE, abstain: tick.weights.ABSTAIN }]
        : [],
    ),
    panel: panelRows(state, view),
    warnings: state.warnings,
  }
}

/**
 * The sheet's reasoning is prose: the summary, then the narrative's bodies — never its `##` marks.
 * A fallback narrative IS the summary (backend §17.3), so it is not printed a second time.
 */
function reasoningOf(view: VerdictView): string[] {
  const written = view.narrativeStatus === 'fallback' ? '' : view.narrative
  return [view.summary, ...splitSections(written).map((section) => section.body)].filter(Boolean)
}

/** R4 — the who-held rows are grouped from the final stances in the frozen order, empty groups dropped. */
function heldViews(view: VerdictView): ReportModel['whoHeldWhichView'] {
  return STANCE_ORDER.map((position) => ({
    position,
    names: view.finalStances.filter((row) => row.stance === position).map((row) => row.agent),
  })).filter((row) => row.names.length > 0)
}

/**
 * The panel matrix, read off the roster the run seated plus the turns it recorded. Position is the
 * expert's final stance when one was filed (the profile's opening stance otherwise); strength is the
 * profile's mean strength, the value the backend now reports where it once reported conviction.
 */
function panelRows(state: RunState, view: VerdictView): ReportModel['panel'] {
  const finalStances = new Map(view.finalStances.map((row) => [row.agent, row.stance]))
  const turns = new Map<string, number>()
  for (const round of state.rounds) {
    for (const turn of round.turns) turns.set(turn.agent_name, (turns.get(turn.agent_name) ?? 0) + 1)
  }
  return state.roster.map((profile) => {
    return {
      name: profile.name,
      role: profile.role,
      position: finalStances.get(profile.name) ?? profile.stance,
      confidence: profile.confidence,
      strength: profile.strength,
      turns: turns.get(profile.name) ?? 0,
    }
  })
}
