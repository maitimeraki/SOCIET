import type { AgentView } from '../../run/events'
import Drawer from '../ui/Drawer'
import PositionMark from '../ui/PositionMark'
import Emphasis from '../common/Emphasis'
import Meter from '../ui/Meter'

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
    <Drawer open={open} onClose={onClose} title={profile.name}>
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <PositionMark position={profile.stance} ground="light" />
          <span className="text-body text-ink-2">{profile.role}</span>
        </div>
        <p className="max-w-[60ch] text-body text-ink-2">{profile.bio}</p>
        <Emphasis text={profile.details} className="max-w-[60ch] whitespace-pre-wrap text-body text-ink" />

        <section className="space-y-2">
          <Meter label="conf" value={profile.confidence} display={profile.confidence.toFixed(2)} />
          <Meter label="str" value={profile.strength} display={profile.strength.toFixed(2)} />
        </section>
      </div>
    </Drawer>
  )
}
