import type { AgentView } from '../../run/events'
import { shownText } from '../../run/agentDisplay'
import Drawer from '../ui/Drawer'
import PositionMark from '../ui/PositionMark'
import Meter from '../ui/Meter'
import { Details, Estimate } from './AgentFacts'

export default function AgentDrawer({
  profile,
  open,
  onClose,
}: {
  profile: AgentView | null
  open: boolean
  onClose: () => void
}) {
  if (!profile) return null
  return (
    <Drawer open={open} onClose={onClose} title={shownText(profile.name)}>
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <PositionMark position={profile.stance} ground="light" />
          <span className="text-body text-ink-2">{shownText(profile.role)}</span>
        </div>
        <p className="max-w-[60ch] text-body text-ink-2">{shownText(profile.bio)}</p>
        <Details text={profile.details} className="max-w-[60ch] space-y-3 text-body text-ink" />

        <section className="space-y-2">
          <Meter label="str" value={profile.strength} display={profile.strength.toFixed(2)} />
          <Estimate value={profile.confidence} />
        </section>
      </div>
    </Drawer>
  )
}
