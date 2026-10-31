import type { Stance } from '../../run/events'
import { asStance } from '../../run/events'
import type { RunRound, RunState } from '../../run/reducer'
import { STANCE_ORDER, verdictView } from '../../run/selectors'
import type { VerdictView } from '../../run/selectors'
import { splitSections } from '../verdict/narrative'
import { fmtDay } from '../../utils/format'
import { sourceTitles } from './AnswerDocument'
import type { ReportModel } from './exportReport'

/**
 * §12.8 / R57 — the one derivation of the filed report from folded run state. The report tab renders
 * this model and every export serializes it, so there is no second writer to drift.
 *
 * Null before a verdict is filed: the tab states that the report is not there yet rather than
 * fabricating one.
 */
export function reportFromState(state: RunState): ReportModel | null {
  const view = verdictView(state)
  if (!view) return null
  return {
    question: state.query || 'This decision',
    filed: filedDay(state),
    position: view.stance,
    share: view.confidence,
    caseAgainst: view.dissentingViews[0]?.view ?? 'No dissent was recorded.',
    reasoning: reasoningOf(view),
    whoHeldWhichView: heldViews(view),
    sources: sourceTitles(state.roster).map((title) => ({ document: title, reference: '' })),
    passes: state.rounds.map(passRow),
    panel: panelRows(state, view),
    warnings: state.warnings,
  }
}

/**
 * The newest moment the folded event buffer recorded — the run's filing day as far as the buffer
 * carries one. No stage recorded = the day is not known, stated as a dash, never invented.
 */
function filedDay(state: RunState): string {
  const newest = state.stages.reduce<number | null>(
    (latest, stage) => (latest === null || stage.at > latest ? stage.at : latest),
    null,
  )
  return newest === null ? '—' : fmtDay(new Date(newest).toISOString())
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

/** One row per pass, from the pass's own consensus weights when it recorded them. */
function passRow(round: RunRound): ReportModel['passes'][number] {
  const weights = round.consensus?.weights ?? turnWeights(round)
  return {
    pass: `P${round.round}`,
    negative: weights.NEGATIVE,
    positive: weights.POSITIVE,
    ambivalent: weights.AMBIVALENT,
  }
}

/** Pre-consensus passes: approximate the share from turn counts, one equal vote per turn. */
function turnWeights(round: RunRound): Record<Stance, number> {
  const counts: Record<Stance, number> = { POSITIVE: 0, NEGATIVE: 0, NEUTRAL: 0, AMBIVALENT: 0 }
  for (const turn of round.turns) counts[asStance(turn.stance)] += 1
  const total = round.turns.length || 1
  return {
    POSITIVE: counts.POSITIVE / total,
    NEGATIVE: counts.NEGATIVE / total,
    NEUTRAL: counts.NEUTRAL / total,
    AMBIVALENT: counts.AMBIVALENT / total,
  }
}

/**
 * The panel matrix, read off the roster the run seated plus the turns it recorded. Position is the
 * expert's final stance when one was filed (the profile's opening stance otherwise); receptivity is
 * the profile's `cior`; weight is the backend's CIOR weight (confidence × conviction × (1 + cior) / 2),
 * derived here because no event carries a per-expert weight.
 */
function panelRows(state: RunState, view: VerdictView): ReportModel['panel'] {
  const finalStances = new Map(view.finalStances.map((row) => [row.agent, row.stance]))
  const turns = new Map<string, number>()
  for (const round of state.rounds) {
    for (const turn of round.turns) turns.set(turn.agent_name, (turns.get(turn.agent_name) ?? 0) + 1)
  }
  return state.roster.map((profile) => {
    const name = profile.identity.name
    return {
      name,
      role: profile.identity.archetype,
      position: finalStances.get(name) ?? profile.stance,
      confidence: profile.confidence,
      conviction: profile.conviction,
      receptivity: profile.cior,
      turns: turns.get(name) ?? 0,
      weight: (profile.confidence * profile.conviction * (1 + profile.cior)) / 2,
    }
  })
}
