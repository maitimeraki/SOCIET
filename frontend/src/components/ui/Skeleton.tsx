/**
 * §8.9 — a skeleton that matches the final dimensions. The shimmer runs at 1.2s between sand and
 * its lit step; there is no spinner.
 */
export default function Skeleton({ className = '' }: { className?: string }) {
  return <div aria-hidden="true" className={`skeleton-shimmer rounded-xs bg-sand ${className}`} />
}
