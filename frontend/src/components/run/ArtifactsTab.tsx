import type { RunEvent } from '../../run/events'
import type { RunState } from '../../run/reducer'
import { fmtScore } from '../../utils/format'
import SelectionTable from './SelectionTable'
import WarningList from '../common/WarningList'

export default function ArtifactsTab({ run, events }: { run: RunState; events: RunEvent[] }) {
  return (
    <div className="space-y-8">
      <section>
        <h2 className="mb-3 text-heading text-paper">Intent (S3)</h2>
        {run.intent ? (
          <dl className="grid grid-cols-[140px_1fr] gap-y-2 text-body">
            <dt className="text-paper-mute">core</dt>
            <dd className="text-paper-dim">{run.intent.core_question}</dd>
            <dt className="text-paper-mute">keywords</dt>
            <dd className="text-paper-dim">{run.intent.direct_keywords.join(', ')}</dd>
            <dt className="text-paper-mute">sectors</dt>
            <dd className="text-paper-dim">{run.intent.latent_sectors.join(', ')}</dd>
            <dt className="text-paper-mute">perspectives</dt>
            <dd className="text-paper-dim">{run.intent.search_perspectives.join(', ')}</dd>
            <dt className="text-paper-mute">confidence</dt>
            <dd className="tnum font-mono text-paper-dim">
              {fmtScore(run.intent.extraction_confidence)} · {run.intent.llm_model || '—'} · {run.intent.llm_provider || '—'}
            </dd>
          </dl>
        ) : (
          <p className="text-body text-paper-mute">No intent event recorded.</p>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-heading text-paper">Selection (S4)</h2>
        {run.selection.length > 0 ? (
          <SelectionTable rows={run.selection} />
        ) : (
          <p className="text-body text-paper-mute">No selection event recorded.</p>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-heading text-paper">Pairs per round</h2>
        {run.rounds.length === 0 && <p className="text-body text-paper-mute">No rounds yet.</p>}
        {run.rounds.map((round) => (
          <div key={round.round} className="mb-4">
            <h3 className="text-body text-paper">Round {round.round}</h3>
            <ul className="mt-1 space-y-1">
              {round.pairs.map((pair, index) => (
                <li key={index} className="text-body text-paper-dim">
                  {pair.agent_a} ↔ {pair.agent_b}
                  {pair.shared_entities.length > 0 && (
                    <span className="text-paper-mute"> · shared: {pair.shared_entities.join(', ')}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>

      <section>
        <h2 className="mb-3 text-heading text-paper">Commits</h2>
        {run.commits.length === 0 && <p className="text-body text-paper-mute">No commits yet.</p>}
        {run.commits.map((commit) => (
          <p key={commit.round} className="tnum font-mono text-mono text-paper-dim">
            R{commit.round} · {commit.opinions} opinions · {commit.edges} edges {commit.failed ? '✕' : '✓'}
          </p>
        ))}
      </section>

      <section>
        <h2 className="mb-3 text-heading text-paper">Warnings ({run.warnings.length})</h2>
        <WarningList warnings={run.warnings} />
      </section>

      <section>
        <h2 className="mb-3 text-heading text-paper">Raw event log</h2>
        <div className="max-h-[420px] overflow-auto rounded-[6px] border border-ink-700 bg-ink-900 p-3">
          {events.length === 0 && <p className="text-body text-paper-mute">No events yet.</p>}
          {events.map((event, index) => (
            <div key={index} className="tnum whitespace-pre-wrap break-all font-mono text-mono leading-[18px] text-paper-dim">
              {String(index).padStart(4, '0')} {event.type} {JSON.stringify(event)}
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
