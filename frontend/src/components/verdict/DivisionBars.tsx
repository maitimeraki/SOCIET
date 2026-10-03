import type { ClusterSummary, Stance } from '../../run/events'
import { STANCE_ORDER } from '../../run/selectors'
import { fmtScore } from '../../utils/format'

const FILL: Record<Stance, string> = {
  POSITIVE: 'bg-stance-pos',
  NEUTRAL: 'bg-stance-neu',
  AMBIVALENT: 'bg-stance-amb',
  NEGATIVE: 'bg-stance-neg',
}

export default function DivisionBars({ clusters }: { clusters: ClusterSummary[] }) {
  const byStance = new Map(clusters.map((cluster) => [cluster.stance, cluster]))
  const maxWeight = Math.max(0.0001, ...clusters.map((cluster) => cluster.total_weight))

  return (
    <div className="space-y-3">
      {STANCE_ORDER.map((stance) => {
        const cluster = byStance.get(stance)
        const weight = cluster?.total_weight ?? 0
        return (
          <div key={stance} className="grid grid-cols-[110px_1fr_auto] items-center gap-3">
            <span className="text-label uppercase text-paper">{stance}</span>
            <div className="h-2 rounded-[4px] bg-ink-800">
              {cluster && weight > 0 && (
                <div className={`h-full rounded-[4px] ${FILL[stance]}`} style={{ width: `${(weight / maxWeight) * 100}%` }} />
              )}
            </div>
            <span className="tnum font-mono text-mono text-paper-dim">
              {cluster
                ? `${cluster.count} agents · ${fmtScore(weight)} weight · ${fmtScore(cluster.avg_confidence)} conf`
                : '0 agents'}
            </span>
          </div>
        )
      })}
      {clusters.length === 0 && <p className="text-body text-paper-mute">No cluster details recorded for this run.</p>}
    </div>
  )
}
