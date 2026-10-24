import { useEffect, useRef } from 'react'
import { CheckCircle, XCircle } from '@phosphor-icons/react'

export type RailStageState = 'pending' | 'running' | 'done' | 'failed'

export interface RailStage {
  key: string
  label: string
  state: RailStageState
  note?: string
}

export default function StageRail({
  stages,
  activeKey,
  onSelect,
}: {
  stages: RailStage[]
  activeKey?: string
  onSelect?: (key: string) => void
}) {
  const rail = useRef<HTMLElement>(null)

  // The rail scrolls inside its own row at 390; the current step must be visible without the customer
  // discovering the scroll. The step change is the motion, so the scroll is instant — not smooth.
  useEffect(() => {
    rail.current
      ?.querySelector('[aria-current="step"]')
      ?.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'auto' })
  }, [activeKey])

  return (
    <nav
      ref={rail}
      aria-label="Run stages"
      // A scroll container that only a pointer can reveal is not reachable by keyboard; focusing the
      // rail lets the arrow keys scroll it.
      tabIndex={0}
      className="flex flex-nowrap items-center gap-x-3 overflow-x-auto border-b border-ink-4 pb-3"
    >
      {stages.map((stage, index) => {
        const glyph =
          stage.state === 'done' ? (
            // Settled is ink, not a stance hue — --color-pos-light is the POSITIVE legend's green and
            // means "a station argued for the proposal", never "this stage finished" (§3.1, §7).
            <CheckCircle size={16} className="text-ink-2" aria-hidden="true" />
          ) : stage.state === 'running' ? (
            <span aria-hidden="true" className="h-2.5 w-2.5 animate-pulse rounded-full bg-accent" />
          ) : stage.state === 'failed' ? (
            <XCircle size={16} className="text-danger" aria-hidden="true" />
          ) : (
            <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full border border-ink-3" />
          )
        const current = stage.key === activeKey
        const inner = (
          <span className={`inline-flex items-center gap-2 whitespace-nowrap ${current ? 'text-ink' : 'text-ink-2'}`}>
            {glyph}
            <span className="text-label uppercase">{stage.label}</span>
            {stage.note && <span className="tnum font-measurement text-micro text-ink-3">{stage.note}</span>}
          </span>
        )
        return (
          <div key={stage.key} className="flex shrink-0 items-center gap-3">
            {index > 0 && <span aria-hidden="true" className="h-px w-4 bg-ink-4" />}
            {onSelect ? (
              <button
                type="button"
                aria-current={current ? 'step' : undefined}
                onClick={() => onSelect(stage.key)}
                className="rounded-[4px] px-1 py-0.5 transition-colors hover:bg-ground-2"
              >
                {inner}
              </button>
            ) : (
              <span aria-current={current ? 'step' : undefined}>{inner}</span>
            )}
          </div>
        )
      })}
    </nav>
  )
}
