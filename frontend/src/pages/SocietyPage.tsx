import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, startDebate } from '../api/rest'
import { DEBATE_CONFIG_DEFAULTS } from '../api/types'
import type { DebateConfig } from '../api/types'
import { useDraftStore } from '../wizard/draftStore'
import StageRail from '../components/common/StageRail'
import QueryComposer from '../components/society/QueryComposer'
import ConfigPanel from '../components/society/ConfigPanel'
import Button from '../components/ui/Button'
import { fmtInt } from '../utils/format'

export default function SocietyPage() {
  const navigate = useNavigate()
  const datasetId = useDraftStore((s) => s.datasetId)
  const corpusName = useDraftStore((s) => s.corpusName)
  const graphSummary = useDraftStore((s) => s.graphSummary)
  const clear = useDraftStore((s) => s.clear)
  const [query, setQuery] = useState('')
  const [config, setConfig] = useState<DebateConfig>(DEBATE_CONFIG_DEFAULTS)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!datasetId) navigate('/new/ingest', { state: { note: "Your session's documents expired — add them again." } })
  }, [datasetId, navigate])

  const convene = async () => {
    if (!query.trim() || !datasetId || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const { job_id } = await startDebate({
        graph_id: datasetId,
        query: query.trim(),
        selected_domains: [],
        simulation_depth: 'standard',
        config,
      })
      clear() // documents are done with; datasetId survives for the run views
      navigate(`/runs/${job_id}/roster`)
    } catch (err) {
      setError(
        err instanceof ApiError && err.status < 500
          ? `The server rejected this run: ${err.detail}`
          : `Couldn't reach the server. Nothing ran — try again.`,
      )
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-[760px] space-y-8">
      <StageRail
        stages={[
          { key: 'ingest', label: 'Ingest', state: 'done' },
          { key: 'graph', label: 'Graph', state: 'done' },
          { key: 'question', label: 'Question', state: 'running' },
        ]}
      />
      <div>
        <p className="text-label uppercase text-paper-mute">Step 3 · Question</p>
        <h1 className="mt-2 font-serif text-display text-paper">Set the question</h1>
        <p className="tnum mt-2 font-mono text-mono text-paper-mute">
          Corpus: {corpusName}
          {graphSummary ? ` (${fmtInt(graphSummary.chunks)} chunks)` : ''}
        </p>
      </div>

      <div>
        <p className="mb-2 text-label uppercase text-paper-mute">What should the society deliberate?</p>
        <QueryComposer value={query} onChange={setQuery} onSubmit={convene} />
        <p className="mt-2 max-w-[60ch] text-micro text-paper-mute">
          The question picks which parts of the graph speak. Broader questions convene more of the society.
        </p>
      </div>

      <ConfigPanel value={config} onChange={setConfig} />

      {error && <p className="rounded-[6px] border border-critical/40 px-4 py-3 text-body text-paper-dim">{error}</p>}

      <div className="flex items-center gap-4">
        <Button variant="primary" loading={submitting} disabled={!query.trim()} onClick={convene}>
          Convene the debate
        </Button>
        <span className="text-micro text-paper-mute">Runs take a few minutes — you can watch every round live.</span>
      </div>
    </div>
  )
}
