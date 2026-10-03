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
  return (
    <nav aria-label="Run stages" className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-ink-700 pb-3">
      {stages.map((stage, index) => {
        const glyph =
          stage.state === 'done' ? (
            <CheckCircle size={16} className="text-good" aria-hidden="true" />
          ) : stage.state === 'running' ? (
            <span aria-hidden="true" className="h-2.5 w-2.5 animate-pulse rounded-full bg-accent" />
          ) : stage.state === 'failed' ? (
            <XCircle size={16} className="text-critical" aria-hidden="true" />
          ) : (
            <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full border border-paper-faint" />
          )
        const current = stage.key === activeKey
        const inner = (
          <span className={`inline-flex items-center gap-2 ${current ? 'text-paper' : 'text-paper-dim'}`}>
            {glyph}
            <span className="text-label uppercase">{stage.label}</span>
            {stage.note && <span className="tnum font-mono text-micro text-paper-mute">{stage.note}</span>}
          </span>
        )
        return (
          <div key={stage.key} className="flex items-center gap-3">
            {index > 0 && <span aria-hidden="true" className="h-px w-4 bg-ink-600" />}
            {onSelect ? (
              <button
                type="button"
                aria-current={current ? 'step' : undefined}
                onClick={() => onSelect(stage.key)}
                className="rounded-[4px] px-1 py-0.5 transition-colors hover:bg-ink-800"
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
