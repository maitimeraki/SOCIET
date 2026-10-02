import type { Stance } from '../../run/events'
import { asStance } from '../../run/events'

export { asStance }

const DOT: Record<Stance, string> = {
  POSITIVE: 'bg-stance-pos',
  NEUTRAL: 'bg-stance-neu',
  AMBIVALENT: 'bg-stance-amb',
  NEGATIVE: 'bg-stance-neg',
}

export function stanceDotClass(stance: Stance): string {
  return DOT[stance]
}

export default function StanceChip({ stance, size = 'md' }: { stance: Stance; size?: 'sm' | 'md' }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-[4px] border border-ink-700 bg-ink-800 text-paper ${
        size === 'sm' ? 'px-1.5 py-0.5 text-micro' : 'px-2 py-1 text-label'
      }`}
    >
      <span aria-hidden="true" className={`h-2 w-2 rounded-full ${DOT[stance]}`} />
      {stance}
    </span>
  )
}
