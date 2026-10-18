import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight } from '@phosphor-icons/react'
import { startGraphBuild, startOntology } from '../api/rest'
import { pollJob } from '../api/poll'
import type { GraphJobResult, JobStatus } from '../api/types'
import { useDraftStore } from '../wizard/draftStore'
import StageLine from '../components/graph/StageLine'
import ProgressBar from '../components/graph/ProgressBar'
import SchemaCard from '../components/graph/SchemaCard'
import RelationTable from '../components/graph/RelationTable'
import StatRow from '../components/graph/StatRow'
import JobError from '../components/graph/JobError'
import Button from '../components/ui/Button'
import { fmtInt } from '../utils/format'

type Phase = 'ontology' | 'build' | 'done' | 'failed'

export default function GraphPage({ onFailureChange }: { onFailureChange?: (failed: boolean) => void }) {
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

  // Report the failure up so the workspace rail shows a failed stage rather than a pulse that would
  // contradict this body's JobError. The phase machine stays here; only the boolean leaves.
  useEffect(() => {
    onFailureChange?.(phase === 'failed')
  }, [phase, onFailureChange])

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
      // R42: `poll.ts` now treats `cancelled` as terminal, so a cancelled job must fail this branch —
      // testing only for `failed` would let it fall through as a success. Graph jobs settle at
      // `completed` (src/jobs/tasks.py), never the debate's `complete`.
      if (ontologyJob.status !== 'completed') {
        setPhase('failed')
        setError(ontologyJob.error ?? 'unknown error')
        return
      }

      let buildId = useDraftStore.getState().graphJobId
      setPhase('build') // before the if: a resumed build (stored job id) must also leave the ontology phase
      if (!buildId) {
        const started = await startGraphBuild(draft.datasetId!, readyDocs, ontologyId)
        buildId = started.job_id
        setJobs({ graphJobId: buildId })
      }
      const buildJob = await pollJob(buildId, applyTick, pollOptions)
      if (buildJob.status !== 'completed') {
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
    // No corpus to build from: do not boot. The workspace's guard returns to the first step with the
    // note IngestPage renders, so this page no longer redirects (it is a step, not a host).
    if (!datasetId || readyCount === 0) return
    if (bootRef.current) return // StrictMode double-invoke guard
    bootRef.current = true
    // eslint-disable-next-line react-hooks/set-state-in-effect -- boot guard: run() owns the phase machine and must start synchronously once per mount
    void run()
    // No abort on unmount: the job continues server-side; the persisted job ids resume it on return (§7.3).
  }, [datasetId, run])

  const rerun = () => {
    setJobs({ ontologyJobId: null, graphJobId: null })
    setError(null)
    setProgress(0)
    setResult(null)
    setPhase('ontology')
    void run()
  }

  const completed = result?.chunks_completed ?? 0
  const total = result?.chunks_total ?? 0

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-titling text-display text-ink">Grow the map</h1>
      </div>

      {reconnecting && (
        <p className="rounded-[4px] border border-warn/40 px-3 py-2 text-micro text-ink">
          Can't reach the server. The work continues on the server — we'll reconnect.
        </p>
      )}

      {phase !== 'done' && phase !== 'failed' && (
        <div className="space-y-4 border-t border-ink-4 pt-5">
          <StageLine
            label="Discovering the kinds of things in your material"
            state={phase === 'ontology' ? 'active' : 'done'}
            helper="Discovery takes about a minute per ten documents."
          />
          <StageLine label="Extracting entities and relations" state={phase === 'build' ? 'active' : 'pending'} />
          {phase === 'build' && (
            <div className="space-y-4">
              <ProgressBar value={progress} label={`${fmtInt(completed)} / ${fmtInt(total)} sections`} />
              <p className="tnum font-measurement text-mono text-ink-2">
                map so far · {fmtInt(result?.entity_types.length ?? 0)} entity types · {fmtInt(result?.relation_types.length ?? 0)} relation types
              </p>
              <p className="text-micro text-ink-3">Each section is written as it finishes — the map grows while the build runs.</p>
            </div>
          )}
        </div>
      )}

      {result && (result.entity_types.length > 0 || result.relation_types.length > 0) && (
        <div className="grid grid-cols-2 gap-4">
          <SchemaCard title="The kinds of things it found" names={result.entity_types} />
          <RelationTable names={result.relation_types} />
        </div>
      )}

      {phase === 'done' && (
        <div className="space-y-6">
          {/* The finished map lives in the workspace's map pane, which stays mounted across the whole
              lifecycle — this surface no longer renders a canvas of its own (D14: one map). */}
          <div>
            <p className="text-heading text-ink">The map is built</p>
            <StatRow
              items={[
                { label: 'Sections', value: fmtInt(result?.chunks_total ?? 0) },
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
