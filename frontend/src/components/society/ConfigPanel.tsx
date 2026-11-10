import { DEBATE_CONFIG_RANGES } from '../../api/types'
import type { DebateConfig } from '../../api/types'
import Disclosure from '../ui/Disclosure'
import Field from '../ui/Field'
import NumberField from '../ui/NumberField'

const FIELD_LABELS: Record<keyof DebateConfig, string> = {
  max_agents: 'Max experts',
  max_rounds: 'Passes',
  comm_radius: 'Comm radius',
  min_entity_overlap: 'Min entity overlap',
  max_pairs_per_round: 'Max pairs per pass',
  convergence_threshold: 'Convergence',
  llm_concurrency: 'Analysis concurrency',
  topology_score_threshold: 'Topology threshold',
  max_new_agents_per_round: 'Max new experts / pass',
  snapshot_top_k: 'Snapshot top-k',
}

export interface PlanLimits {
  max_agents: number
  max_rounds: number
}

/**
 * The field's ceiling is the plan cap when the plan is tighter than the server's absolute bound.
 * The server still rejects an over-cap request; this panel must not offer one.
 */
// eslint-disable-next-line react-refresh/only-export-components -- fieldMax is the tested cap rule
export function fieldMax(key: keyof DebateConfig, limits?: PlanLimits): number {
  const range = DEBATE_CONFIG_RANGES[key]
  if (key === 'max_agents') return Math.min(range.max, limits?.max_agents ?? range.max)
  if (key === 'max_rounds') return Math.min(range.max, limits?.max_rounds ?? range.max)
  return range.max
}

export default function ConfigPanel({
  value,
  onChange,
  limits,
}: {
  value: DebateConfig
  onChange: (next: DebateConfig) => void
  limits?: PlanLimits
}) {
  return (
    <Disclosure summary={<span className="text-body text-ink-2">Deliberation settings</span>}>
      <div className="grid grid-cols-2 gap-x-8 gap-y-4">
        {(Object.keys(DEBATE_CONFIG_RANGES) as (keyof DebateConfig)[]).map((key) => {
          const range = DEBATE_CONFIG_RANGES[key]
          const max = fieldMax(key, limits)
          return (
            <Field key={key} label={FIELD_LABELS[key]} hint={`${range.min}–${max}`}>
              <NumberField
                value={value[key]}
                min={range.min}
                max={max}
                step={range.step ?? 1}
                onChange={(next) => onChange({ ...value, [key]: next })}
              />
            </Field>
          )
        })}
      </div>
    </Disclosure>
  )
}
