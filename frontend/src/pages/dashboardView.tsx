import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
// Imported by path, and there is no `../ui` barrel any more: Drawer's framer-motion import would
// otherwise ride into this module — and this module is what the node-only dashboard test renders
// (R45: framer-motion in a test is a measured cost).
import Band from '../components/ui/Band'
import { StateChip } from '../components/ui/Chip'
import { buttonClasses } from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import { ruleClasses } from '../components/ui/Rule'
import SectionHeading from '../components/ui/SectionHeading'
import { DASHBOARD_ANCHORS } from './dashboardAnchors'
import { DASHBOARD_COPY } from './dashboardCopy'

export interface DashboardViewProps {
  /** True when the account holds no material and no decisions: one state, one action (§14.3). */
  accountEmpty: boolean
  /** The running decision, when there is one: the live band is this one line, never a floor. */
  live: { runId: string; question: string } | null
  material: ReactNode
  decisions: ReactNode
  lastAnswer: ReactNode
  panel: ReactNode
}

/**
 * The dashboard's one surface (§14.3), presentational: the page title, the one action, the live
 * line, and the four sections in the lifecycle's own order — Your material · Your decisions · The
 * last answer · Your panel. Each section is separated by a rule; only The last answer takes a
 * band, the plum one, because plum means *the answer*.
 *
 * The sections arrive as slots so this module stays free of their data flow (and of the graph
 * stack), and so the node-only suite can render the page's own structure without a browser.
 */
export default function DashboardView({
  accountEmpty,
  live,
  material,
  decisions,
  lastAnswer,
  panel,
}: DashboardViewProps) {
  return (
    <div>
      <header className={`${ruleClasses('bottom')} flex flex-wrap items-end justify-between gap-4 pb-8`}>
        <div>
          <h1 className="font-titling text-display text-ink">{DASHBOARD_COPY.title}</h1>
          <p className="mt-2 max-w-[60ch] text-body text-ink-2">{DASHBOARD_COPY.lead}</p>
          <p className="mt-1 text-micro text-ink-3">{DASHBOARD_COPY.trust}</p>
        </div>
        {/* The one action. On an empty account it lives in the empty block, so there is exactly one. */}
        {!accountEmpty && (
          <Link to="/new" className={buttonClasses('primary', 40, 'min-h-11')}>
            {DASHBOARD_COPY.startFree}
          </Link>
        )}
      </header>

      {live && (
        <div data-capture="live" className={`${ruleClasses('bottom')} flex items-center gap-3 py-3`}>
          <StateChip state="running" />
          <Link
            to={`/runs/${live.runId}`}
            className="inline-flex min-h-11 min-w-0 items-center truncate text-body text-ink-2 hover:text-accent"
          >
            {live.question}
          </Link>
        </div>
      )}

      {accountEmpty ? (
        <div className="pt-10">
          <EmptyState
            line={DASHBOARD_COPY.empty.account}
            action={
              <Link to="/new" className={buttonClasses('primary', 40, 'min-h-11')}>
                {DASHBOARD_COPY.startFree}
              </Link>
            }
          />
        </div>
      ) : (
        <>
          <section id={DASHBOARD_ANCHORS.material} aria-labelledby="material-heading" className="py-10">
            <SectionHeading
              id="material-heading"
              title={DASHBOARD_COPY.sections.material.title}
              lead={DASHBOARD_COPY.sections.material.lead}
            />
            {material}
          </section>

          <section
            id={DASHBOARD_ANCHORS.decisions}
            aria-labelledby="decisions-heading"
            className={`${ruleClasses('both')} py-10`}
          >
            <SectionHeading
              id="decisions-heading"
              title={DASHBOARD_COPY.sections.decisions.title}
              lead={DASHBOARD_COPY.sections.decisions.lead}
            />
            {decisions}
          </section>

          <Band
            tone="plum"
            dense
            id={DASHBOARD_ANCHORS.lastAnswer}
            aria-labelledby="last-answer-heading"
          >
            <SectionHeading
              id="last-answer-heading"
              title={DASHBOARD_COPY.sections.lastAnswer.title}
              lead={DASHBOARD_COPY.sections.lastAnswer.lead}
            />
            {lastAnswer}
          </Band>

          <section
            id={DASHBOARD_ANCHORS.panel}
            aria-labelledby="panel-heading"
            className={`${ruleClasses('both')} py-10`}
          >
            <SectionHeading
              id="panel-heading"
              title={DASHBOARD_COPY.sections.panel.title}
              lead={DASHBOARD_COPY.sections.panel.lead}
            />
            {panel}
          </section>
        </>
      )}
    </div>
  )
}
