import type { ReactNode } from 'react'

/**
 * §10.3 The output side of the split — the work. It holds the step's surface; it owns no behaviour
 * of its own. It is not a card: the split is one instrument, edge to edge, so the pane carries the
 * paper ground and neither a radius nor a shadow.
 *
 * It is hidden with `hidden` when the map is expanded, never unmounted, so returning to split does not
 * remount the work either. On stacked widths it sits above the map (§9 responsive) and takes the right
 * column once the panes sit side by side.
 */
export default function ActivityPane({ hidden, children }: { hidden?: boolean; children: ReactNode }) {
  return (
    <section aria-label="The work" hidden={hidden} className="min-h-full min-w-0 bg-paper px-6 pb-12 pt-6">
      {/* §6.2 Enter — the work fades and rises once each time the pane is restored. */}
      <div className="enter">{children}</div>
    </section>
  )
}
