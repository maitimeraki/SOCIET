export default function Skeleton({ className = '' }: { className?: string }) {
  return <div aria-hidden="true" className={`animate-pulse rounded-[4px] bg-ground-2 ${className}`} />
}
