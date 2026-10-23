import type { AgentProfile } from '../../run/events'
import Drawer from '../ui/Drawer'
import PositionMark from '../ui/PositionMark'
import Emphasis from '../common/Emphasis'
import Meter from '../ui/Meter'
import ProvenanceList from './ProvenanceList'

export default function AgentDrawer({
  profile,
  open,
  onClose,
}: {
  profile: AgentProfile | null
  open: boolean
  onClose: () => void
}) {
  if (!profile) return null
  const breakdown = profile.confidence_breakdown
  const breakdownMax = Math.max(breakdown.source_breadth, breakdown.node_density, 1)
  return (
    <Drawer open={open} onClose={onClose} title={profile.identity.name}>
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <PositionMark position={profile.stance} ground="light" />
          <span className="text-body text-ink-2">{profile.identity.archetype}</span>
        </div>
        <p className="max-w-[60ch] text-body text-ink-2">{profile.bio}</p>
        <Emphasis text={profile.detailed_perspective} className="max-w-[60ch] whitespace-pre-wrap text-body-lg text-ink" />

        <section>
          <h3 className="mb-2 text-label uppercase text-ink-3">Confidence breakdown</h3>
          <div className="space-y-2">
            <Meter label="src" value={breakdown.source_breadth} max={breakdownMax} display={String(breakdown.source_breadth)} />
            <Meter label="nnd" value={breakdown.node_density} max={breakdownMax} display={String(breakdown.node_density)} />
            <Meter label="rlc" value={breakdown.relationship_connectivity} display={breakdown.relationship_connectivity.toFixed(2)} />
          </div>
        </section>

        <section>
          <h3 className="mb-2 text-label uppercase text-ink-3">Provenance</h3>
          <ProvenanceList links={profile.summary_provenance ?? []} />
        </section>

        {profile.graph_snapshot && (
          <section>
            <h3 className="mb-2 text-label uppercase text-ink-3">Map snapshot</h3>
            <p className="tnum font-measurement text-mono text-ink-2">
              {profile.graph_snapshot.dataset_id} · {profile.graph_snapshot.chunk_count} sections ·{' '}
              {profile.graph_snapshot.version_hash.slice(0, 8)}
            </p>
          </section>
        )}
      </div>
    </Drawer>
  )
}
