import { Check, X } from '@phosphor-icons/react'
import type { RunEvent } from '../../run/events'
import type { RunState } from '../../run/reducer'
import { fmtScore } from '../../utils/format'
import DefinitionList from '../ui/DefinitionList'
import SelectionTable from './SelectionTable'
import EventLog from './EventLog'
import WarningList from '../common/WarningList'

export default function ArtifactsTab({ run, events }: { run: RunState; events: RunEvent[] }) {
  return (
    <div className="space-y-8">
      <section>
        <h2 className="mb-3 text-heading text-ink">Intent (S3)</h2>
        {run.intent ? (
          <DefinitionList
            items={[
              { term: 'core', value: run.intent.core_question },
              { term: 'keywords', value: run.intent.direct_keywords.join(', ') },
              { term: 'sectors', value: run.intent.latent_sectors.join(', ') },
              { term: 'perspectives', value: run.intent.search_perspectives.join(', ') },
              {
                term: 'confidence',
                value: (
                  <span className="tnum font-measurement">
                    {fmtScore(run.intent.extraction_confidence)} · {run.intent.llm_model || '—'} · {run.intent.llm_provider || '—'}
                  </span>
                ),
              },
            ]}
          />
        ) : (
          <p className="text-body text-ink-3">No intent event recorded.</p>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-heading text-ink">Selection (S4)</h2>
        {run.selection.length > 0 ? (
          <SelectionTable rows={run.selection} />
        ) : (
          <p className="text-body text-ink-3">No selection event recorded.</p>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-heading text-ink">Pairs per pass</h2>
        {run.rounds.length === 0 && <p className="text-body text-ink-3">No passes yet.</p>}
        {run.rounds.map((round) => (
          <div key={round.round} className="mb-4">
            <h3 className="text-body text-ink">Pass {round.round}</h3>
            <ul className="mt-1 space-y-1">
              {round.pairs.map((pair, index) => (
                <li key={index} className="text-body text-ink-2">
                  {pair.agent_a} ↔ {pair.agent_b}
                  {pair.shared_entities.length > 0 && (
                    <span className="text-ink-3"> · shared: {pair.shared_entities.join(', ')}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>

      <section>
        <h2 className="mb-3 text-heading text-ink">Commits</h2>
        {run.commits.length === 0 && <p className="text-body text-ink-3">No commits yet.</p>}
        {run.commits.map((commit) => (
          <p key={commit.round} className="tnum flex items-center gap-1 font-measurement text-mono text-ink-2">
            P{commit.round} · {commit.opinions} opinions · {commit.edges} connections
            {commit.failed ? <X size={12} aria-hidden="true" /> : <Check size={12} aria-hidden="true" />}
            <span className="sr-only">{commit.failed ? 'failed' : 'kept'}</span>
          </p>
        ))}
      </section>

      <section>
        <h2 className="mb-3 text-heading text-ink">Warnings ({run.warnings.length})</h2>
        <WarningList warnings={run.warnings} />
      </section>

      <section>
        <h2 className="mb-3 text-heading text-ink">Raw event log</h2>
        <EventLog events={events} />
      </section>
    </div>
  )
}
