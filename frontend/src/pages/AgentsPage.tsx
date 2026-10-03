import { useEffect, useMemo, useState } from 'react'
import { getRun, listRuns } from '../api/rest'
import type { AgentProfile } from '../run/events'
import AgentCard from '../components/agents/AgentCard'
import AgentDrawer from '../components/agents/AgentDrawer'
import Select from '../components/ui/Select'
import EmptyState from '../components/ui/EmptyState'
import Skeleton from '../components/ui/Skeleton'

export default function AgentsPage() {
  const [datasets, setDatasets] = useState<{ id: string; runId: string }[]>([])
  const [datasetId, setDatasetId] = useState<string>('')
  const [roster, setRoster] = useState<AgentProfile[]>([])
  const [runsLoaded, setRunsLoaded] = useState(false)
  const [loadedDatasetId, setLoadedDatasetId] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const loading = !runsLoaded || (datasetId !== '' && loadedDatasetId !== datasetId)

  useEffect(() => {
    listRuns()
      .then((runs) => {
        const seen = new Map<string, string>()
        for (const run of runs) if (!seen.has(run.dataset_id)) seen.set(run.dataset_id, run.run_id)
        const entries = [...seen.entries()].map(([id, runId]) => ({ id, runId }))
        setDatasets(entries)
        if (entries.length > 0) setDatasetId(entries[0].id)
        setRunsLoaded(true)
      })
      .catch(() => setRunsLoaded(true))
  }, [])

  useEffect(() => {
    const entry = datasets.find((dataset) => dataset.id === datasetId)
    if (!entry) return
    getRun(entry.runId)
      .then((doc) => {
        const profiles = doc.events.flatMap((event) => (event.type === 'agent' ? [event.profile] : []))
        setRoster(profiles)
      })
      .catch(() => setRoster([]))
      .finally(() => setLoadedDatasetId(datasetId))
  }, [datasetId, datasets])

  const profile = selected ? roster.find((entry) => entry.identity.name === selected) ?? null : null
  const note = useMemo(() => {
    const entry = datasets.find((dataset) => dataset.id === datasetId)
    return entry ? `Showing the society from run ${entry.runId} — agents are synthesized per question.` : ''
  }, [datasets, datasetId])

  return (
    <div className="space-y-6">
      <h1 className="font-serif text-display text-paper">Agents</h1>
      {datasets.length > 1 && (
        <Select value={datasetId} onChange={(event) => setDatasetId(event.target.value)} aria-label="Choose corpus">
          {datasets.map((dataset) => (
            <option key={dataset.id} value={dataset.id}>
              {dataset.id}
            </option>
          ))}
        </Select>
      )}
      {note && <p className="tnum font-mono text-mono text-paper-mute">{note}</p>}
      {loading ? (
        <div className="grid gap-3 md:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
      ) : roster.length === 0 ? (
        <EmptyState line="No society yet. Convene a run and the agents it synthesizes will be shown here." />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {roster.map((entry) => (
            <AgentCard key={entry.agent_id} profile={entry} onOpen={() => setSelected(entry.identity.name)} />
          ))}
        </div>
      )}
      <AgentDrawer profile={profile} open={profile !== null} onClose={() => setSelected(null)} />
    </div>
  )
}
