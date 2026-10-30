import type { ReactNode } from 'react'
import Card from '../ui/Card'

/**
 * §9.4 The activity pane — the work. It holds the step's surface; it owns no behaviour of its own.
 *
 * It is hidden with `hidden` when the map is expanded, never unmounted, so returning to split does not
 * remount the work either. On stacked widths it sits above the map (§9 responsive) and takes the right
 * column once the panes sit side by side. The pane is the kit's `Card`, so its 16px radius is the same
 * 16px the map pane sits against — one seam, one radius (§14.4).
 */
export default function ActivityPane({ hidden, children }: { hidden?: boolean; children: ReactNode }) {
  return (
    <Card as="section" aria-label="The work" hidden={hidden} className="order-1 min-w-0 lg:order-2">
      {/* §6.2 Enter — the work fades and rises once each time the pane is restored. */}
      <div className="enter">{children}</div>
    </Card>
  )
}
