import type { ReactNode } from 'react'

/**
 * §9.4 The activity pane — the work. It holds the step's surface; it owns no behaviour of its own.
 *
 * It is hidden with `hidden` when the map is expanded, never unmounted, so returning to split does not
 * remount the work either. On stacked widths it sits above the map (§9 responsive) and takes the right
 * column once the panes sit side by side.
 */
export default function ActivityPane({ hidden, children }: { hidden?: boolean; children: ReactNode }) {
  return (
    <section
      aria-label="The work"
      hidden={hidden}
      className="order-1 min-w-0 rounded-lg border border-border bg-canvas p-4 lg:order-2"
    >
      {children}
    </section>
  )
}
