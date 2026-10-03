import { DEBATE_CONFIG_RANGES } from '../../api/types'
import type { DebateConfig } from '../../api/types'
import Disclosure from '../ui/Disclosure'
import Field from '../ui/Field'
import NumberField from '../ui/NumberField'

const FIELD_LABELS: Record<keyof DebateConfig, string> = {
  max_agents: 'Max agents',
  max_rounds: 'Rounds',
  comm_radius: 'Comm radius',
  min_entity_overlap: 'Min entity overlap',
  max_pairs_per_round: 'Max pairs per round',
  convergence_threshold: 'Convergence',
  llm_concurrency: 'LLM concurrency',
  topology_score_threshold: 'Topology threshold',
  max_new_agents_per_round: 'Max new agents / round',
  snapshot_top_k: 'Snapshot top-k',
}

export default function ConfigPanel({ value, onChange }: { value: DebateConfig; onChange: (next: DebateConfig) => void }) {
  return (
    <Disclosure summary={<span className="text-body text-paper-dim">Deliberation settings</span>}>
      <div className="grid grid-cols-2 gap-x-8 gap-y-4">
        {(Object.keys(DEBATE_CONFIG_RANGES) as (keyof DebateConfig)[]).map((key) => {
          const range = DEBATE_CONFIG_RANGES[key]
          return (
            <Field key={key} label={FIELD_LABELS[key]} hint={`${range.min}–${range.max}`}>
              <NumberField
                value={value[key]}
                min={range.min}
                max={range.max}
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
