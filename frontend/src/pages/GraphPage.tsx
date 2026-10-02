import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight } from '@phosphor-icons/react'
import { startGraphBuild, startOntology } from '../api/rest'
import { pollJob } from '../api/poll'
import type { GraphJobResult, JobStatus } from '../api/types'
import { useDraftStore } from '../wizard/draftStore'
import StageRail from '../components/common/StageRail'
import StageLine from '../components/graph/StageLine'
import ProgressBar from '../components/graph/ProgressBar'
import SchemaCard from '../components/graph/SchemaCard'
import RelationTable from '../components/graph/RelationTable'
import StatRow from '../components/graph/StatRow'
import JobError from '../components/graph/JobError'
import Button from '../components/ui/Button'
import { fmtInt } from '../utils/format'

type Phase = 'ontology' | 'build' | 'done' | 'failed'

export default function GraphPage() {
  const navigate = useNavigate()
  const datasetId = useDraftStore((s) => s.datasetId)
  const setJobs = useDraftStore((s) => s.setJobs)
  const setGraphSummary = useDraftStore((s) => s.setGraphSummary)
  const [phase, setPhase] = useState<Phase>('ontology')
  const [progress, setProgress] = useState(0)
  const [result, setResult] = useState<GraphJobResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reconnecting, setReconnecting] = useState(false)
  const bootRef = useRef(false)

  const applyTick = useCallback((job: JobStatus) => {
    setProgress(job.progress)
    if (job.result) setResult(job.result)
  }, [])

  const run = useCallback(async () => {
    const draft = useDraftStore.getState()
    const readyDocs = draft.docs.filter((doc) => doc.status === 'ready')
    const pollOptions = { onBackoff: () => setReconnecting(true), onRecover: () => setReconnecting(false) }
    try {
      let ontologyId = draft.ontologyJobId
      if (!ontologyId) {
        setPhase('ontology')
        const started = await startOntology(draft.datasetId!, readyDocs)
        ontologyId = started.job_id
        setJobs({ ontologyJobId: ontologyId })
      }
      const ontologyJob = await pollJob(ontologyId, applyTick, pollOptions)
      if (ontologyJob.status === 'failed') {
        setPhase('failed')
        setError(ontologyJob.error ?? 'unknown error')
        return
      }

      let buildId = useDraftStore.getState().graphJobId
      setPhase('build') // before the if: a resumed build (stored job id) must also leave the ontology phase
      if (!buildId) {
        const started = await startGraphBuild(draft.datasetId!, readyDocs)
        buildId = started.job_id
        setJobs({ graphJobId: buildId })
      }
      const buildJob = await pollJob(buildId, applyTick, pollOptions)
      if (buildJob.status === 'failed') {
        setPhase('failed')
        setError(buildJob.error ?? 'unknown error')
        return
      }

      const summary = buildJob.result ?? null
      setResult(summary)
      if (summary) {
        setGraphSummary({
          chunks: summary.chunks_total,
          docs: summary.docs_built,
          entityTypes: summary.entity_types.length,
          relationTypes: summary.relation_types.length,
        })
      }
      setPhase('done')
    } catch (err) {
      setPhase('failed')
      setError(err instanceof Error ? err.message : 'unknown error')
    }
  }, [applyTick, setGraphSummary, setJobs])

  useEffect(() => {
    const draft = useDraftStore.getState()
    const readyCount = draft.docs.filter((doc) => doc.status === 'ready').length
    if (!datasetId || readyCount === 0) {
      navigate('/new/ingest', { state: { note: "Your session's documents expired — add them again." } })
      return
    }
    if (bootRef.current) return // StrictMode double-invoke guard
    bootRef.current = true
    void run()
    // No abort on unmount: the job continues server-side; the persisted job ids resume it on return (§7.3).
  }, [datasetId, navigate, run])

  const rerun = () => {
    setJobs({ ontologyJobId: null, graphJobId: null })
    setError(null)
    setProgress(0)
    setResult(null)
    setPhase('ontology')
    void run()
  }

  const railStages = [
    { key: 'ingest', label: 'Ingest', state: 'done' as const },
    { key: 'graph', label: 'Graph', state: phase === 'done' ? ('done' as const) : phase === 'failed' ? ('failed' as const) : ('running' as const) },
    { key: 'question', label: 'Question', state: 'pending' as const },
  ]

  const completed = result?.chunks_completed ?? 0
  const total = result?.chunks_total ?? 0

  return (
    <div className="mx-auto max-w-[760px] space-y-8">
      <StageRail stages={railStages} />
      <div>
        <p className="text-label uppercase text-paper-mute">Step 2 · Graph</p>
        <h1 className="mt-2 font-serif text-display text-paper">Grow the knowledge graph</h1>
      </div>

      {reconnecting && (
        <p className="rounded-[4px] border border-brass/40 px-3 py-2 text-micro text-brass">
          Can't reach the server. The job continues on the server — we'll reconnect.
        </p>
      )}

      {phase !== 'done' && phase !== 'failed' && (
        <div className="space-y-4 rounded-[6px] border border-ink-700 bg-ink-900 p-5">
          <StageLine
            label="Discovering the ontology"
            state={phase === 'ontology' ? 'active' : 'done'}
            helper="Discovery takes about a minute per ten documents."
          />
          <StageLine label="Extracting entities and relations" state={phase === 'build' ? 'active' : 'pending'} />
          {phase === 'build' && (
            <div className="space-y-2">
              <ProgressBar value={progress} label={`${fmtInt(completed)} / ${fmtInt(total)} chunks`} />
              <p className="tnum font-mono text-mono text-paper-dim">
                graph so far · {fmtInt(result?.entity_types.length ?? 0)} entity types · {fmtInt(result?.relation_types.length ?? 0)} relation types
              </p>
              <p className="text-micro text-paper-mute">Each chunk is written as it finishes — the graph grows while the build runs.</p>
            </div>
          )}
        </div>
      )}

      {result && (result.entity_types.length > 0 || result.relation_types.length > 0) && (
        <div className="grid grid-cols-2 gap-4">
          <SchemaCard title="The ontology it discovered" names={result.entity_types} />
          <RelationTable names={result.relation_types} />
        </div>
      )}

      {phase === 'done' && (
        <div className="space-y-6">
          <div>
            <p className="text-heading text-paper">Graph built</p>
            <StatRow
              items={[
                { label: 'Chunks', value: fmtInt(result?.chunks_total ?? 0) },
                { label: 'Documents', value: fmtInt(result?.docs_built ?? 0) },
                { label: 'Entity types', value: fmtInt(result?.entity_types.length ?? 0) },
                { label: 'Relation types', value: fmtInt(result?.relation_types.length ?? 0) },
              ]}
            />
          </div>
          <Button variant="primary" onClick={() => navigate('/new/society')}>
            Set the question
            <ArrowRight size={16} aria-hidden="true" />
          </Button>
        </div>
      )}

      {phase === 'failed' && <JobError error={error ?? 'unknown error'} onRerun={rerun} />}
    </div>
  )
}
