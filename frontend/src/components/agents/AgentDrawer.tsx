import type { AgentProfile } from '../../run/events'
import Drawer from '../ui/Drawer'
import StanceChip from '../common/StanceChip'
import MeterBar from './MeterBar'
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
          <StanceChip stance={profile.stance} />
          <span className="text-body text-paper-dim">{profile.identity.archetype}</span>
        </div>
        <p className="max-w-[60ch] text-body text-paper-dim">{profile.bio}</p>
        <p className="max-w-[60ch] whitespace-pre-wrap text-body-lg text-paper">{profile.detailed_perspective}</p>

        <section>
          <h3 className="mb-2 text-label uppercase text-paper-mute">Confidence breakdown</h3>
          <div className="space-y-2">
            <MeterBar label="src" value={breakdown.source_breadth} max={breakdownMax} display={String(breakdown.source_breadth)} />
            <MeterBar label="nnd" value={breakdown.node_density} max={breakdownMax} display={String(breakdown.node_density)} />
            <MeterBar label="rlc" value={breakdown.relationship_connectivity} display={breakdown.relationship_connectivity.toFixed(2)} />
          </div>
        </section>

        <section>
          <h3 className="mb-2 text-label uppercase text-paper-mute">Provenance</h3>
          <ProvenanceList links={profile.summary_provenance ?? []} />
        </section>

        {profile.graph_snapshot && (
          <section>
            <h3 className="mb-2 text-label uppercase text-paper-mute">Graph snapshot</h3>
            <p className="tnum font-mono text-mono text-paper-dim">
              {profile.graph_snapshot.dataset_id} · {profile.graph_snapshot.chunk_count} chunks ·{' '}
              {profile.graph_snapshot.version_hash.slice(0, 8)}
            </p>
          </section>
        )}
      </div>
    </Drawer>
  )
}
